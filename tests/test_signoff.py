import os
from solver_sch.ai.auto_designer import AutonomousDesigner

def test_signoff_flow():
    print("=== Testing LTspice Sign-off Flow ===")
    # Target: 6V Output from 12V Supply (Voltage Divider)
    # We use a simple goal that the AI can solve in 1-2 iterations.
    goal = "[DC TARGET: 6.0V] Design a simple voltage divider to get 6V from 12V input. [MAX CURRENT: 10mA]"
    
    designer = AutonomousDesigner(goal)
    
    # We only need to run the loop. 
    # The integration in auto_designer.py will trigger LTspiceVerifier on SUCCESS.
    try:
        designer.run_optimization_loop(max_iterations=5)
        print("\nFlow Test Complete.")
    except Exception as e:
        print(f"\nFlow Test CRASHED: {e}")

if __name__ == "__main__":
    # Ensure GEMINI_API_KEY is present
    if "GEMINI_API_KEY" not in os.environ:
        print("Error: GEMINI_API_KEY not set.")
    else:
        test_signoff_flow()
