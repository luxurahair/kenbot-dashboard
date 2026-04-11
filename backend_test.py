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
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)

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
                print(f"   Response: {response.text[:200]}")
                self.failed_tests.append(f"{name}: Expected {expected_status}, got {response.status_code}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append(f"{name}: {str(e)}")
            return False, {}

    def test_system_status(self):
        """Test system status endpoint"""
        success, response = self.run_test(
            "System Status",
            "GET",
            "api/system/status",
            200
        )
        if success:
            # Validate response structure
            required_fields = ['version', 'services', 'stats', 'last_run']
            for field in required_fields:
                if field not in response:
                    print(f"❌ Missing field: {field}")
                    return False
            
            # Check stats structure
            stats = response.get('stats', {})
            if 'inventory' not in stats or 'posts' not in stats:
                print(f"❌ Missing inventory or posts in stats")
                return False
                
            print(f"   Inventory: {stats['inventory']}")
            print(f"   Posts: {stats['posts']}")
            return True
        return False

    def test_cron_runs(self):
        """Test cron runs endpoint"""
        success, response = self.run_test(
            "Cron Runs",
            "GET",
            "api/cron/runs",
            200
        )
        if success and isinstance(response, list):
            print(f"   Found {len(response)} cron runs")
            if len(response) > 0:
                run = response[0]
                required_fields = ['run_id', 'status', 'inv_count', 'timestamp']
                for field in required_fields:
                    if field not in run:
                        print(f"❌ Missing field in cron run: {field}")
                        return False
            return True
        return False

    def test_inventory(self):
        """Test inventory endpoint"""
        success, response = self.run_test(
            "Inventory",
            "GET",
            "api/inventory",
            200
        )
        if success and isinstance(response, list):
            print(f"   Found {len(response)} inventory items")
            if len(response) > 0:
                item = response[0]
                required_fields = ['slug', 'stock', 'title', 'status']
                for field in required_fields:
                    if field not in item:
                        print(f"❌ Missing field in inventory item: {field}")
                        return False
            return True
        return False

    def test_posts(self):
        """Test posts endpoint"""
        success, response = self.run_test(
            "Posts",
            "GET",
            "api/posts",
            200
        )
        if success and isinstance(response, list):
            print(f"   Found {len(response)} posts")
            if len(response) > 0:
                post = response[0]
                required_fields = ['slug', 'stock', 'status', 'no_photo']
                for field in required_fields:
                    if field not in post:
                        print(f"❌ Missing field in post: {field}")
                        return False
                print(f"   Posts with no_photo: {sum(1 for p in response if p.get('no_photo'))}")
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
            if len(response) > 0:
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
    print("🚀 Starting Kenbot Dashboard API Tests")
    print("=" * 50)
    
    tester = KenbotAPITester()
    
    # Run all tests
    tests = [
        tester.test_system_status,
        tester.test_cron_runs,
        tester.test_inventory,
        tester.test_posts,
        tester.test_changelog,
        tester.test_architecture,
    ]
    
    for test in tests:
        test()
    
    # Print results
    print("\n" + "=" * 50)
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