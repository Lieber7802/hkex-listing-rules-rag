import argparse
import json
from pathlib import Path
import httpx

from app.core.config import settings
from app.core.logger import logger


def run_demo_queries(
    queries_file: Path,
    api_base_url: str,
    output_file: Path = None
):
    queries_file = Path(queries_file)
    
    with open(queries_file, 'r', encoding='utf-8') as f:
        queries = json.load(f)
    
    results = []
    
    for query_item in queries:
        query_id = query_item.get('id', 'unknown')
        query_text = query_item['query']
        expected_type = query_item.get('type', 'unknown')
        
        logger.info(f"Running query [{query_id}]: {query_text[:50]}...")
        
        try:
            response = httpx.post(
                f"{api_base_url}/chat",
                json={"query": query_text},
                timeout=60.0
            )
            
            if response.status_code == 200:
                data = response.json()
                result = {
                    "query_id": query_id,
                    "query": query_text,
                    "expected_type": expected_type,
                    "actual_type": data.get("query_type"),
                    "answer": data.get("answer"),
                    "citations_count": len(data.get("citations", [])),
                    "retrieved_chunks_count": len(data.get("retrieved_chunks", [])),
                    "uncertainty_note": data.get("uncertainty_note"),
                    "success": True
                }
            else:
                result = {
                    "query_id": query_id,
                    "query": query_text,
                    "expected_type": expected_type,
                    "error": f"API returned {response.status_code}",
                    "success": False
                }
        
        except Exception as e:
            result = {
                "query_id": query_id,
                "query": query_text,
                "expected_type": expected_type,
                "error": str(e),
                "success": False
            }
        
        results.append(result)
        
        if result["success"]:
            print(f"\n{'='*60}")
            print(f"Query [{query_id}]: {query_text}")
            print(f"Type: {result['actual_type']} (expected: {expected_type})")
            print(f"Answer: {result['answer'][:200]}...")
            print(f"Citations: {result['citations_count']}")
            print(f"{'='*60}\n")
        else:
            print(f"\nQuery [{query_id}] FAILED: {result.get('error')}\n")
    
    if output_file:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"Results saved to {output_file}")
    
    success_count = sum(1 for r in results if r["success"])
    print(f"\nSummary: {success_count}/{len(queries)} queries succeeded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run demo queries against the API")
    parser.add_argument("--queries-file", type=str, default=str(settings.demo_dir / "sample_queries.json"),
                        help="JSON file containing sample queries")
    parser.add_argument("--api-url", type=str, default="http://localhost:8000",
                        help="Base URL for the API")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file for results")
    
    args = parser.parse_args()
    
    run_demo_queries(
        Path(args.queries_file),
        args.api_url,
        Path(args.output) if args.output else None
    )