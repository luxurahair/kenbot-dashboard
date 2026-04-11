import requests
import sys
from datetime import datetime

class KenbotAPITester:
    def __init__(self, base_url="https://kenebec-ai.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def run_test(self, name, method, endpoint, expected_status, data=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:300]}")
                self.failed_tests.append(f"{name}: Expected {expected_status}, got {response.status_code}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append(f"{name}: {str(e)}")
            return False, {}

    def test_system_status(self):
        """Test system status endpoint - should show supabase_connected=true and real counts"""
        success, response = self.run_test(
            "System Status",
            "GET",
            "api/system/status",
            200
        )
        if success:
            # Validate response structure
            required_fields = ['version', 'supabase_connected', 'stats']
            for field in required_fields:
                if field not in response:
                    print(f"❌ Missing field: {field}")
                    return False
            
            # Check Supabase connection
            if not response.get('supabase_connected'):
                print(f"❌ Supabase not connected")
                return False
            else:
                print(f"   ✅ Supabase connected: {response['supabase_connected']}")
            
            # Check stats structure and expected counts
            stats = response.get('stats', {})
            if 'inventory' not in stats or 'posts' not in stats or 'events' not in stats:
                print(f"❌ Missing inventory, posts, or events in stats")
                return False
                
            inv = stats['inventory']
            posts = stats['posts']
            events = stats['events']
            
            print(f"   Inventory: total={inv.get('total', 0)}, active={inv.get('active', 0)}, sold={inv.get('sold', 0)}")
            print(f"   Posts: total={posts.get('total', 0)}, active={posts.get('active', 0)}")
            print(f"   Events: total={events.get('total', 0)}")
            
            # Validate expected counts (approximately)
            if inv.get('total', 0) < 70:  # Should be around 76
                print(f"❌ Inventory total too low: {inv.get('total', 0)} (expected ~76)")
                return False
            if posts.get('total', 0) < 80:  # Should be around 86
                print(f"❌ Posts total too low: {posts.get('total', 0)} (expected ~86)")
                return False
            if events.get('total', 0) < 30000:  # Should be around 31,955
                print(f"❌ Events total too low: {events.get('total', 0)} (expected ~31,955)")
                return False
                
            return True
        return False

    def test_inventory(self):
        """Test inventory endpoint - should return real vehicle data from Supabase"""
        success, response = self.run_test(
            "Inventory",
            "GET",
            "api/inventory",
            200
        )
        if success and isinstance(response, list):
            print(f"   Found {len(response)} inventory items")
            if len(response) == 0:
                print(f"❌ No inventory items found")
                return False
                
            # Check expected count (should be around 76)
            if len(response) < 70:
                print(f"❌ Inventory count too low: {len(response)} (expected ~76)")
                return False
                
            # Validate structure of first item
            item = response[0]
            required_fields = ['stock', 'title', 'price_int', 'km_int', 'vin', 'status']
            for field in required_fields:
                if field not in item:
                    print(f"❌ Missing field in inventory item: {field}")
                    return False
                    
            # Check for ACTIVE and SOLD statuses
            active_count = sum(1 for item in response if item.get('status') == 'ACTIVE')
            sold_count = sum(1 for item in response if item.get('status') == 'SOLD')
            print(f"   Active vehicles: {active_count}, Sold vehicles: {sold_count}")
            
            return True
        return False

    def test_posts(self):
        """Test posts endpoint - should return real Facebook posts from Supabase"""
        success, response = self.run_test(
            "Posts",
            "GET",
            "api/posts",
            200
        )
        if success and isinstance(response, list):
            print(f"   Found {len(response)} posts")
            if len(response) == 0:
                print(f"❌ No posts found")
                return False
                
            # Check expected count (should be around 86)
            if len(response) < 80:
                print(f"❌ Posts count too low: {len(response)} (expected ~86)")
                return False
                
            # Validate structure of first post
            post = response[0]
            required_fields = ['slug', 'post_id', 'status', 'published_at']
            for field in required_fields:
                if field not in post:
                    print(f"❌ Missing field in post: {field}")
                    return False
                    
            # Check for posts with no_photo flag
            no_photo_count = sum(1 for p in response if p.get('no_photo'))
            active_count = sum(1 for p in response if p.get('status') == 'ACTIVE')
            print(f"   Active posts: {active_count}, Posts with no_photo: {no_photo_count}")
            
            return True
        return False

    def test_events(self):
        """Test events endpoint - should return real events with type, slug, created_at, payload"""
        success, response = self.run_test(
            "Events",
            "GET",
            "api/events",
            200
        )
        if success and isinstance(response, list):
            print(f"   Found {len(response)} events")
            if len(response) == 0:
                print(f"❌ No events found")
                return False
                
            # Validate structure of first event
            event = response[0]
            required_fields = ['type', 'slug', 'created_at']
            for field in required_fields:
                if field not in event:
                    print(f"❌ Missing field in event: {field}")
                    return False
                    
            # Check event types
            event_types = set(e.get('type') for e in response if e.get('type'))
            print(f"   Event types found: {list(event_types)[:5]}...")  # Show first 5 types
            
            return True
        return False

    def test_changelog(self):
        """Test changelog endpoint"""
        success, response = self.run_test(
            "Changelog",
            "GET",
            "api/changelog",
            200
        )
        if success and isinstance(response, list):
            print(f"   Found {len(response)} changelog entries")
            if len(response) == 0:
                print(f"❌ No changelog entries found")
                return False
                
            # Validate structure of first entry
            entry = response[0]
            required_fields = ['version', 'date', 'type', 'title', 'changes']
            for field in required_fields:
                if field not in entry:
                    print(f"❌ Missing field in changelog entry: {field}")
                    return False
                    
            # Check for v2.1.0 PHOTOS_ADDED bugfix
            v210_entry = next((e for e in response if e.get('version') == '2.1.0'), None)
            if v210_entry and len(v210_entry.get('changes', [])) == 3:
                print(f"   ✅ Found v2.1.0 with 3 changes")
            else:
                print(f"   ❌ v2.1.0 entry not found or doesn't have 3 changes")
                
            return True
        return False

    def test_architecture(self):
        """Test architecture endpoint"""
        success, response = self.run_test(
            "Architecture",
            "GET",
            "api/architecture",
            200
        )
        if success and isinstance(response, dict):
            required_fields = ['components', 'flows', 'states']
            for field in required_fields:
                if field not in response:
                    print(f"❌ Missing field in architecture: {field}")
                    return False
            
            states = response.get('states', [])
            expected_states = ['NEW', 'SOLD', 'RESTORE', 'PRICE_CHANGED', 'PHOTOS_ADDED']
            if set(states) == set(expected_states):
                print(f"   ✅ All expected states found: {states}")
            else:
                print(f"   ❌ States mismatch. Expected: {expected_states}, Got: {states}")
                
            print(f"   Components: {len(response.get('components', []))}")
            print(f"   Flows: {len(response.get('flows', []))}")
            return True
        return False

def main():
    print("🚀 Starting Kenbot Dashboard API Tests (Supabase Live Data)")
    print("=" * 60)
    
    tester = KenbotAPITester()
    
    # Run all tests
    tests = [
        tester.test_system_status,
        tester.test_inventory,
        tester.test_posts,
        tester.test_events,
        tester.test_changelog,
        tester.test_architecture,
    ]
    
    for test in tests:
        test()
    
    # Print results
    print("\n" + "=" * 60)
    print(f"📊 Tests Results: {tester.tests_passed}/{tester.tests_run} passed")
    
    if tester.failed_tests:
        print("\n❌ Failed Tests:")
        for failure in tester.failed_tests:
            print(f"   - {failure}")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed!")
        return 0
    else:
        print("💥 Some tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())