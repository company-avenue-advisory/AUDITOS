from pydantic import BaseModel

class M(BaseModel):
    v: float

try:
    print(M(v='29,784.58'))
except Exception as e:
    print(e)
