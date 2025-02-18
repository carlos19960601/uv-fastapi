from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(tags=["login"])


@router.post("/login/access-token")
def login_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    print(
        f"{form_data.username} {form_data.password}",
    )
    pass
