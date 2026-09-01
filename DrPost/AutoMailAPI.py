from doctest import debug

import Worker
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

doctor = Worker.DrMail("drmailsender@gmail.com", "qczt avra wzbw nbnj")

app = FastAPI()
allow_list = [
        "*"
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/send_mail")
def send_mail(data :dict):
    try:
        doctor.SendMail(
            data["from"],
            data["to"],
            data["sub"],
            data["msg_content"]
        )

        return {"status": "success"}

    except Exception as err:
        raise Exception(err)
        return {
            "status": "error",
            "error": str(err)
        }

@app.post("/send_multiple_mail")
def send_multiple_mail(data :dict):
    try:
        doctor.SendMultipleMailAPI(
            data["from"],
            data["to"],
            data["sub"],
            data["msg_content"]
        )

        return {"status": "success"}

    except Exception as err:
        raise Exception(err)
        return {
            "status": "error",
            "error": str(err)
        }

if __name__ == "__main__":
    uvicorn.run(app)
