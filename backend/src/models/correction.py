from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,Text,JSON,Numeric,DateTime,func
from datetime import datetime
from decimal import Decimal
from ..config.database import Base
class Correction(Base):
    __tablename__='corrections'
    id:Mapped[int]=mapped_column(primary_key=True)
    client_key:Mapped[str]=mapped_column(String(64),unique=True)
    customer:Mapped[str]=mapped_column(String(120))
    route:Mapped[str|None]=mapped_column(String(120),nullable=True)
    delta_per_invoice:Mapped[Decimal]=mapped_column(Numeric(12,2))
    declared_delta:Mapped[Decimal]=mapped_column(Numeric(12,2))
    reason:Mapped[str]=mapped_column(String(500))
    status:Mapped[str]=mapped_column(String(20),default='pending')
    basis_hash:Mapped[str]=mapped_column(String(64))
    trial:Mapped[dict]=mapped_column(JSON)
    reject_reason:Mapped[str|None]=mapped_column(String(300),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    decided_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
