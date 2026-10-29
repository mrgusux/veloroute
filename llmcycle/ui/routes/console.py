from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from .deps import auth, llm_client
from .models import TestCompleteRequest

router = APIRouter()

@router.post("/api/v1/complete")
async def test_complete(req: TestCompleteRequest, _: str = Depends(auth)):
    try:
        resp = await llm_client.complete(
            model=req.model,
            prompt=req.prompt,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            max_retries=req.max_retries,
            retry_delay=req.retry_delay,
        )
        return {
            "content": resp.content,
            "provider": resp.provider,
            "model": resp.model,
            "latency_ms": round(resp.latency_ms, 1),
            "tokens": {"prompt": resp.prompt_tokens, "completion": resp.completion_tokens},
        }
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/api/v1/stream")
async def test_stream(
    model: str = Query(...),
    prompt: str = Query(...),
    max_retries: int = Query(2),
    retry_delay: float = Query(1.0),
    _: str = Depends(auth),
):
    async def event_generator():
        try:
            async for chunk in llm_client.stream(
                model=model,
                prompt=prompt,
                max_retries=max_retries,
                retry_delay=retry_delay,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {e}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
