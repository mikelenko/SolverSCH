import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver_sch.ai.tools import tool_query_datasheet, REGISTRY

async def test_robustness():
    print("Testing tool_query_datasheet with part_number alias...")
    # This should now work instead of erroring with "unexpected keyword argument"
    result = await tool_query_datasheet(part_number="LM5085", query="feedback voltage")
    
    if "error" in result:
        print(f"FAILED: {result['error']}")
    else:
        print("SUCCESS: tool_query_datasheet handled 'part_number' correctly.")
        print(f"Result count: {len(result.get('results', []))}")

    print("\nTesting REGISTRY.call robustness...")
    # Test through the registry
    result_reg = await REGISTRY.call("query_datasheet", {"part_number": "LM5085", "query": "feedback"})
    if "error" in result_reg:
        print(f"FAILED (Registry): {result_reg['error']}")
    else:
        print("SUCCESS: REGISTRY.call handled the async call and parameter alias.")

if __name__ == "__main__":
    asyncio.run(test_robustness())
