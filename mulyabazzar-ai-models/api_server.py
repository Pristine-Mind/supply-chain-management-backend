import math

import uvicorn
from engine.inference import get_hybrid_recommendations
from fastapi import FastAPI, HTTPException, Query

app = FastAPI(
    title="MulyaBazzar AI Graph API",
    description="NeurIPS-Aligned B2B Recommendation Engine with Pagination",
    version="1.0.0",
)


@app.get("/")
def health_check():
    return {"status": "AI Engine is Online"}


@app.get("/api/v1/recommend/{user_id}")
def recommend_b2b_matches(
    user_id: int,
    location: str = Query("Kathmandu", description="Target location for boost. Defaults to Kathmandu."),
    page: int = Query(1, ge=1, description="Page number for results"),
    size: int = Query(10, ge=1, le=100, description="Number of results per page"),
):
    try:
        all_recommendations = get_hybrid_recommendations(user_id=user_id, target_location=location)

        if not all_recommendations:
            raise HTTPException(status_code=404, detail=f"User ID {user_id} not found in the AI Graph.")
        total_items = len(all_recommendations)
        total_pages = math.ceil(total_items / size)
        start_idx = (page - 1) * size
        end_idx = start_idx + size
        paginated_results = all_recommendations[start_idx:end_idx]
        return {
            "metadata": {
                "user_id": user_id,
                "applied_location_boost": location,
                "pagination": {
                    "total_items": total_items,
                    "total_pages": total_pages,
                    "current_page": page,
                    "page_size": size,
                    "has_next_page": page < total_pages,
                    "has_previous_page": page > 1,
                },
            },
            "results": paginated_results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    print("Starting FastAPI Server with Pagination")
    uvicorn.run(app, host="0.0.0.0", port=8000)
