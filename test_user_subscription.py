"""Test script to verify user subscription fields work correctly"""

from app import create_app, db
from app.models.user import User

def test_user_subscription_fields():
    """Test that user subscription fields can be accessed without errors"""
    app = create_app()
    with app.app_context():
        # Try to query a user (assuming 'Mbumwae' exists from the error)
        user = User.query.filter_by(username='Mbumwae').first()

        if user:
            print(f"✅ User found: {user.username}")
            print(f"✅ Subscription tier: {user.subscription_tier}")
            print(f"✅ Subscription status: {user.subscription_status}")
            print(f"✅ Trial ends at: {user.trial_ends_at}")
            print(f"✅ Subscription expires at: {user.subscription_expires_at}")
            print(f"✅ Stripe customer ID: {user.stripe_customer_id}")
            print("✅ All subscription fields are accessible!")
            return True
        else:
            print("❌ User 'Mbumwae' not found in database")
            return False

if __name__ == "__main__":
    success = test_user_subscription_fields()
    if success:
        print("\n🎉 User subscription fields test PASSED!")
    else:
        print("\n❌ User subscription fields test FAILED!")
