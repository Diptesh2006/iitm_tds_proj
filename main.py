from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_analyzer import analyze_error_with_ai
from executor import execute_python_code

app = FastAPI(title="AI-Powered Python Code Interpreter")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


class CodeRequest(BaseModel):
    code: str


class CodeResponse(BaseModel):
    error: list[int]
    result: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/code-interpreter", response_model=CodeResponse)
def code_interpreter(request: CodeRequest) -> CodeResponse:
    execution = execute_python_code(request.code)
    if execution["success"]:
        return CodeResponse(error=[], result=execution["output"])
    return CodeResponse(error=analyze_error_with_ai(request.code, execution["output"]), result=execution["output"])
