from pydantic import BaseModel,Field
from decimal import Decimal
class CorrectionInput(BaseModel):
    client_key:str=Field(min_length=8,max_length=64)
    customer:str=Field(min_length=2,max_length=120)
    route:str|None=Field(default=None,max_length=120)
    delta_per_invoice:Decimal=Field(gt=Decimal('-10000'),lt=Decimal('10000'))
    declared_delta:Decimal=Field(gt=Decimal('-10000000'),lt=Decimal('10000000'))
    sample_ids:list[int]=Field(min_length=1,max_length=8)
    reason:str=Field(min_length=2,max_length=500)
