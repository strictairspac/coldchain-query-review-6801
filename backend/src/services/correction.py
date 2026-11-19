"""单客户运费更正：先试算、按样本核对差额、并发拒绝、幂等入账。

试算与入账都在同一事务内完成"锁客户 → 记录依据 → 样本改前 → 改账 → 样本改后"，
试算事务整体回滚（对普通复核不可见）；入账事务把账单 UPDATE 与核对凭证一起提交。
样本 SQL 仍走 validate_sql 白名单，并在 query_reader 角色、2500ms 超时、1000 行上限下执行。
"""
import hashlib,json
from datetime import datetime
from decimal import Decimal,ROUND_HALF_UP,InvalidOperation
from sqlalchemy import select,text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from ..models.correction import Correction
from ..models.sample import Sample
from .query_engine import validate_sql
CENT=Decimal('0.01')
def money(x):return Decimal(str(x)).quantize(CENT,rounding=ROUND_HALF_UP)
def serialize(x):return {'id':x.id,'client_key':x.client_key,'customer':x.customer,'route':x.route,'delta_per_invoice':str(x.delta_per_invoice),'declared_delta':str(x.declared_delta),'reason':x.reason,'status':x.status,'basis_hash':x.basis_hash,'trial':x.trial,'reject_reason':x.reject_reason,'created_at':str(x.created_at),'decided_at':str(x.decided_at) if x.decided_at else None}
def list_corrections(db):return [serialize(x) for x in db.scalars(select(Correction).order_by(Correction.id.desc()))]
def options(db):
    customers=db.execute(text('SELECT DISTINCT customer FROM invoices ORDER BY customer')).scalars().all()
    routes=db.execute(text('SELECT DISTINCT route FROM invoices ORDER BY route')).scalars().all()
    return {'customers':customers,'routes':routes}
def _lock_customer(db,customer):
    db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:c)::bigint)'),{'c':customer})
def _basis(db,customer):
    rows=db.execute(text('SELECT invoice_id, route, amount, temperature, status FROM invoices WHERE customer=:c ORDER BY invoice_id'),{'c':customer}).fetchall()
    return hashlib.sha256(json.dumps([[str(v) for v in row] for row in rows],ensure_ascii=False).encode()).hexdigest()
def _sample_total(db,sql):
    cursor=db.execute(text(validate_sql(sql)))
    rows=cursor.fetchmany(1001)
    if len(rows)>1000:raise ValueError('样本结果超过 1000 行，请聚合或 LIMIT')
    total=Decimal('0')
    for row in rows:
        for v in row:
            if v is None:continue
            try:total+=Decimal(str(v))
            except (InvalidOperation,ValueError):pass
    return total
def _run_trial(db,customer,route,delta,samples):
    """单事务内试算；提交或回滚由调用方决定。行锁只落在该客户账单上，其他客户照常读写。"""
    _lock_customer(db,customer)
    basis=_basis(db,customer)
    db.execute(text("SET LOCAL statement_timeout='2500ms'"))
    db.execute(text('SET LOCAL ROLE query_reader'))
    before={s.id:_sample_total(db,s.original_sql) for s in samples}
    db.execute(text('SET LOCAL ROLE NONE'))
    matched=db.execute(text('UPDATE invoices SET amount=amount+:d WHERE customer=:c'+(' AND route=:r' if route else '')),{'d':delta,'c':customer,'r':route}).rowcount
    db.execute(text('SET LOCAL ROLE query_reader'))
    after={s.id:_sample_total(db,s.original_sql) for s in samples}
    db.execute(text('SET LOCAL ROLE NONE'))
    return basis,before,after,matched
def _detail(samples,before,after,declared):
    details=[];all_match=True
    for s in samples:
        diff=money(after[s.id]-before[s.id]);ok=diff==declared;all_match=all_match and ok
        details.append({'sample_id':s.id,'name':s.name,'before':str(money(before[s.id])),'after':str(money(after[s.id])),'difference':str(diff),'declared':str(declared),'match':ok})
    return details,all_match
def _trial_json(customer,route,delta,declared,matched,basis,details,all_match):
    return {'customer':customer,'route':route,'delta_per_invoice':str(delta),'declared_delta':str(declared),'matched_invoices':matched,'basis_hash':basis,'samples':details,'all_match':all_match,'computed_at':datetime.now().isoformat(timespec='seconds')}
def _samples(db,ids):
    samples=[db.get(Sample,i) for i in ids]
    if any(s is None for s in samples):raise HTTPException(404,'样本不存在')
    return samples
def create_correction(db,data):
    existing=db.scalar(select(Correction).where(Correction.client_key==data.client_key))
    if existing:return serialize(existing),200
    opts=options(db)
    if data.customer not in opts['customers']:raise HTTPException(422,'客户不存在于账单')
    route=data.route or None
    if route and route not in opts['routes']:raise HTTPException(422,'路线不存在于账单')
    ids=list(dict.fromkeys(data.sample_ids))
    samples=_samples(db,ids)
    delta=money(data.delta_per_invoice)
    if delta==0:raise HTTPException(422,'每张调整金额不能为 0')
    declared=money(data.declared_delta)
    basis,before,after,matched=_run_trial(db,data.customer,route,delta,samples)
    details,all_match=_detail(samples,before,after,declared)
    trial=_trial_json(data.customer,route,delta,declared,matched,basis,details,all_match)
    db.rollback()# 试算改动全部回滚，普通复核与其他会话看不到
    obj=Correction(client_key=data.client_key,customer=data.customer,route=route,delta_per_invoice=delta,declared_delta=declared,reason=data.reason,status='pending' if all_match else 'rejected',basis_hash=basis,trial=trial,reject_reason=None if all_match else '申报差额与试算差额不符，未入账',decided_at=None if all_match else datetime.now())
    db.add(obj)
    try:db.commit()
    except IntegrityError:# 同一 client_key 并发/重试已落库，返回既有记录，不重复建单
        db.rollback()
        return serialize(db.scalar(select(Correction).where(Correction.client_key==data.client_key))),200
    return serialize(obj),201
def post_correction(db,ident):
    obj=db.get(Correction,ident)
    if not obj:raise HTTPException(404,'更正批次不存在')
    if obj.status!='pending':return serialize(obj)# 幂等：响应丢失后重试直接返回现状，不重复改账
    _lock_customer(db,obj.customer)
    db.refresh(obj)# 拿到客户级锁后重读，串行化同一客户的并发入账
    if obj.status!='pending':
        db.rollback()
        return serialize(obj)
    ids=[s['sample_id'] for s in obj.trial['samples']]
    samples=_samples(db,ids)
    delta=Decimal(obj.trial['delta_per_invoice']);declared=Decimal(obj.trial['declared_delta'])
    basis,before,after,matched=_run_trial(db,obj.customer,obj.route,delta,samples)
    if basis!=obj.basis_hash:
        db.rollback()
        obj.status='rejected';obj.reject_reason='试算依据已变化：该客户账单在试算后被并发修改，本批更正拒绝入账';obj.decided_at=datetime.now()
        db.commit()
        return serialize(obj)
    details,all_match=_detail(samples,before,after,declared)
    obj.trial=_trial_json(obj.customer,obj.route,delta,declared,matched,basis,details,all_match)
    if not all_match:
        db.rollback()
        obj.status='rejected';obj.reject_reason='入账前复核差额与申报不符，未入账';obj.decided_at=datetime.now()
        db.commit()
        return serialize(obj)
    obj.status='posted';obj.decided_at=datetime.now()
    db.commit()# 账单 UPDATE 与核对凭证（本记录）在同一事务生效
    return serialize(obj)
