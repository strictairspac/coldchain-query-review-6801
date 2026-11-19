from fastapi import APIRouter,Depends,Response
from ..config.database import get_db
from ..schemas.correction import CorrectionInput
from ..services.auth import current_user,writer
from ..services.correction import list_corrections,options,create_correction,post_correction
router=APIRouter(prefix='/corrections')
@router.get('')
def listing(db=Depends(get_db),user=Depends(current_user)):return list_corrections(db)
@router.get('/options')
def opts(db=Depends(get_db),user=Depends(current_user)):return options(db)
@router.post('',status_code=201)
def create(data:CorrectionInput,response:Response,db=Depends(get_db),user=Depends(writer)):
    result,code=create_correction(db,data)
    response.status_code=code
    return result
@router.post('/{ident}/post')
def post(ident:int,db=Depends(get_db),user=Depends(writer)):return post_correction(db,ident)
