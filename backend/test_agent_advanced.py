import asyncio
from backend.app.core.agent import agent_app

async def test_agent():
    print("--- Testing Agent Workflow ---")
    
    # 1. Test with a known false claim (simulated)
    input_text = "The moon is made of green cheese and was built by aliens in 1950."
    
    print(f"\nInput: {input_text}")
    inputs = {"input_text": input_text, "image_bytes": None}
    
    try:
        result = await agent_app.ainvoke(inputs)
        print("\n--- Final Report ---")
        print(result["final_report"])
        print(f"Is Misinformation: {result['is_misinformation']}")
        print(f"Confidence: {result['confidence_score']}")
        
    except Exception as e:
        print(f"Agent failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_agent())
