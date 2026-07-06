import sys
import os

# Add the modules directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'market_dashboard'))

def test_imports():
    """Test importing all modules"""
    try:
        print("Testing imports...")

        # Test data module
        from modules import data
        print("Γ£à data module imported")

        # Test indicators module
        from modules import indicators
        print("Γ£à indicators module imported")

        # Test strategies module
        from modules import strategies
        print("Γ£à strategies module imported")

        # Test portfolio module
        from modules import portfolio
        print("Γ£à portfolio module imported")

        # Test simulator module
        from modules import simulator
        print("Γ£à simulator module imported")

        # Test other modules
        from modules import utils
        print("Γ£à utils module imported")

        from modules import optimizer
        print("Γ£à optimizer module imported")

        from modules import persistence
        print("Γ£à persistence module imported")

        from modules import stock_search
        print("Γ£à stock_search module imported")

        print("All modules imported successfully!")

    except Exception as e:
        print(f"Γ¥î Import error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_imports()
