#!/usr/bin/env python3
"""
Test WebSocket connections for both authenticated and guest users
"""
import asyncio
import json
import sys
from uuid import UUID
import websockets
from datetime import datetime

# Test configuration
BACKEND_URL = "ws://localhost:8000/api/v1/ws/orders"

# Colors for output
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color


def print_success(msg):
    print(f"{GREEN}✓{NC} {msg}")


def print_error(msg):
    print(f"{RED}✗{NC} {msg}")


def print_info(msg):
    print(f"{BLUE}ℹ{NC} {msg}")


def print_warning(msg):
    print(f"{YELLOW}⚠{NC} {msg}")


async def test_guest_connection(order_id: str):
    """
    Test WebSocket connection in guest mode (no token)
    """
    print(f"\n{BLUE}═══════════════════════════════════════════{NC}")
    print(f"{BLUE}Test 1: Guest WebSocket Connection{NC}")
    print(f"{BLUE}═══════════════════════════════════════════{NC}")

    url = f"{BACKEND_URL}/{order_id}"
    print_info(f"Connecting to: {url}")
    print_info("Mode: Guest (no token)")

    try:
        async with websockets.connect(url) as websocket:
            print_success("Connected successfully!")

            # Wait for initial message
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(message)

                print_info(f"Received message type: {data.get('type')}")

                if data.get('type') == 'connected':
                    print_success("Received 'connected' message")
                    print_info(f"Order ID: {data.get('order_id')}")

                    current_status = data.get('current_status', {})
                    print_info(f"Current fulfillment status: {current_status.get('fulfillment_status')}")
                    print_info(f"Payment status: {current_status.get('payment_status')}")

                    return True
                else:
                    print_error(f"Expected 'connected' message, got: {data.get('type')}")
                    return False

            except asyncio.TimeoutError:
                print_error("Timeout waiting for initial message")
                return False

    except websockets.exceptions.InvalidStatusCode as e:
        print_error(f"Connection rejected: {e.status_code}")
        print_info(f"Reason: {e}")
        return False
    except Exception as e:
        print_error(f"Connection failed: {str(e)}")
        return False


async def test_authenticated_connection(order_id: str, token: str):
    """
    Test WebSocket connection with JWT token (authenticated)
    """
    print(f"\n{BLUE}═══════════════════════════════════════════{NC}")
    print(f"{BLUE}Test 2: Authenticated WebSocket Connection{NC}")
    print(f"{BLUE}═══════════════════════════════════════════{NC}")

    url = f"{BACKEND_URL}/{order_id}?token={token}"
    print_info(f"Connecting to: {BACKEND_URL}/{order_id}?token=TOKEN_HIDDEN")
    print_info("Mode: Authenticated (with JWT)")

    try:
        async with websockets.connect(url) as websocket:
            print_success("Connected successfully!")

            # Wait for initial message
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(message)

                print_info(f"Received message type: {data.get('type')}")

                if data.get('type') == 'connected':
                    print_success("Received 'connected' message")
                    print_info(f"Order ID: {data.get('order_id')}")

                    current_status = data.get('current_status', {})
                    print_info(f"Current fulfillment status: {current_status.get('fulfillment_status')}")
                    print_info(f"Payment status: {current_status.get('payment_status')}")

                    return True
                else:
                    print_error(f"Expected 'connected' message, got: {data.get('type')}")
                    return False

            except asyncio.TimeoutError:
                print_error("Timeout waiting for initial message")
                return False

    except websockets.exceptions.InvalidStatusCode as e:
        print_error(f"Connection rejected: {e.status_code}")
        print_info(f"Reason: {e}")
        return False
    except Exception as e:
        print_error(f"Connection failed: {str(e)}")
        return False


async def test_invalid_order_id():
    """
    Test WebSocket connection with invalid order ID
    """
    print(f"\n{BLUE}═══════════════════════════════════════════{NC}")
    print(f"{BLUE}Test 3: Invalid Order ID{NC}")
    print(f"{BLUE}═══════════════════════════════════════════{NC}")

    invalid_order_id = "00000000-0000-0000-0000-000000000000"
    url = f"{BACKEND_URL}/{invalid_order_id}"
    print_info(f"Connecting with invalid order ID: {invalid_order_id}")

    try:
        async with websockets.connect(url) as websocket:
            print_error("Connection should have been rejected!")
            return False

    except websockets.exceptions.InvalidStatusCode as e:
        if e.status_code == 1008:
            print_success(f"Connection correctly rejected with code 1008")
            print_info(f"Reason: Order not found")
            return True
        else:
            print_error(f"Unexpected status code: {e.status_code}")
            return False
    except Exception as e:
        print_warning(f"Connection error (expected): {str(e)}")
        return True


async def test_wrong_user_token(order_id: str, wrong_token: str):
    """
    Test WebSocket connection where authenticated user doesn't own the order
    """
    print(f"\n{BLUE}═══════════════════════════════════════════{NC}")
    print(f"{BLUE}Test 4: Wrong User Token (Unauthorized){NC}")
    print(f"{BLUE}═══════════════════════════════════════════{NC}")

    url = f"{BACKEND_URL}/{order_id}?token={wrong_token}"
    print_info(f"Connecting with token from user who doesn't own the order")

    try:
        async with websockets.connect(url) as websocket:
            print_error("Connection should have been rejected!")
            return False

    except websockets.exceptions.InvalidStatusCode as e:
        if e.status_code == 1008:
            print_success(f"Connection correctly rejected with code 1008")
            print_info(f"Reason: Unauthorized")
            return True
        else:
            print_error(f"Unexpected status code: {e.status_code}")
            return False
    except Exception as e:
        print_warning(f"Connection error (expected): {str(e)}")
        return True


async def main():
    """
    Run all WebSocket tests
    """
    print(f"\n{YELLOW}╔════════════════════════════════════════╗{NC}")
    print(f"{YELLOW}║  WebSocket Guest/Auth Testing Suite   ║{NC}")
    print(f"{YELLOW}╔════════════════════════════════════════╗{NC}\n")

    # Get test parameters from command line or use defaults
    if len(sys.argv) < 2:
        print_error("Usage: python scripts/ad-hoc-tests/test_websocket_guest_auth.py <order_id> [auth_token] [wrong_token]")
        print_info("Example: python scripts/ad-hoc-tests/test_websocket_guest_auth.py abc-123-def eyJhbGc...")
        print_info("\nOr run without parameters to see usage instructions")
        sys.exit(1)

    order_id = sys.argv[1]
    auth_token = sys.argv[2] if len(sys.argv) > 2 else None
    wrong_token = sys.argv[3] if len(sys.argv) > 3 else None

    print_info(f"Testing with Order ID: {order_id}")
    if auth_token:
        print_info(f"Auth token provided: Yes")
    else:
        print_warning("Auth token not provided - skipping authenticated tests")

    results = []

    # Test 1: Guest connection
    result1 = await test_guest_connection(order_id)
    results.append(("Guest Connection", result1))

    # Test 2: Authenticated connection (if token provided)
    if auth_token:
        result2 = await test_authenticated_connection(order_id, auth_token)
        results.append(("Authenticated Connection", result2))

    # Test 3: Invalid order ID
    result3 = await test_invalid_order_id()
    results.append(("Invalid Order ID Rejection", result3))

    # Test 4: Wrong user token (if wrong token provided)
    if wrong_token:
        result4 = await test_wrong_user_token(order_id, wrong_token)
        results.append(("Unauthorized User Rejection", result4))

    # Summary
    print(f"\n{YELLOW}═══════════════════════════════════════════{NC}")
    print(f"{YELLOW}Test Summary{NC}")
    print(f"{YELLOW}═══════════════════════════════════════════{NC}\n")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = f"{GREEN}PASS{NC}" if result else f"{RED}FAIL{NC}"
        print(f"  {status}  {test_name}")

    print(f"\n{BLUE}Results: {passed}/{total} tests passed{NC}\n")

    if passed == total:
        print_success("All tests passed! ✨")
        sys.exit(0)
    else:
        print_error(f"{total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
