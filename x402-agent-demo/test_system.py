#!/usr/bin/env python3
"""
Test script to verify all components
"""

import sys
import os
import requests
import json
from colorama import init, Fore, Style
from dotenv import load_dotenv

init()

load_dotenv()

MOCK_SERVICE_PORT = os.getenv("MOCK_SERVICE_PORT", "5000")
MOCK_SERVICE_BASE_URL = f"http://localhost:{MOCK_SERVICE_PORT}"


def print_success(msg):
    print(f"{Fore.GREEN}✓ {msg}{Style.RESET_ALL}")


def print_error(msg):
    print(f"{Fore.RED}✗ {msg}{Style.RESET_ALL}")


def print_info(msg):
    print(f"{Fore.CYAN}ℹ {msg}{Style.RESET_ALL}")


def test_mock_service():
    """Test if mock service is running"""
    print("\n" + "=" * 60)
    print("Testing Mock x402 Service")
    print("=" * 60)

    try:
        # Test health endpoint
        response = requests.get(f"{MOCK_SERVICE_BASE_URL}/health", timeout=2)
        if response.status_code == 200:
            print_success("Mock service is running")
            print_info(f"Response: {response.json()}")
        else:
            print_error(f"Unexpected status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Mock service is not running!")
        print_info("Start it with: uv run python run_mock_service.py")
        return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

    # Test 402 response
    try:
        response = requests.get(f"{MOCK_SERVICE_BASE_URL}/api/article/test-123")
        if response.status_code == 402:
            print_success("HTTP 402 Payment Required works correctly")
            print_info(
                f"Payment Amount: {response.headers.get('X-Payment-Amount')} {response.headers.get('X-Payment-Currency')}"
            )
            print_info(f"Payment Address: {response.headers.get('X-Payment-Address')}")
        else:
            print_error(f"Expected 402, got {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error testing 402: {e}")
        return False

    # Test with payment proof
    try:
        headers = {
            "X-Payment-Proof": json.dumps(
                {"tx_hash": "0x1234567890abcdef1234567890abcdef"}
            )
        }
        response = requests.get(
            f"{MOCK_SERVICE_BASE_URL}/api/article/test-123", headers=headers
        )
        if response.status_code == 200:
            print_success("Payment verification works correctly")
            content = response.json()
            print_info(f"Received content: {content.get('title', 'N/A')}")
        else:
            print_error(f"Expected 200 after payment, got {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error testing payment: {e}")
        return False

    return True


def test_dependencies():
    """Test if all dependencies are installed"""
    print("\n" + "=" * 60)
    print("Testing Dependencies")
    print("=" * 60)

    dependencies = [
        ("flask", "Flask"),
        ("anthropic", "Anthropic"),
        ("web3", "Web3"),
        ("eth_account", "eth-account"),
        ("dotenv", "python-dotenv"),
        ("telegram", "python-telegram-bot"),
    ]

    all_ok = True
    for module_name, package_name in dependencies:
        try:
            __import__(module_name)
            print_success(f"{package_name} installed")
        except ImportError:
            print_error(f"{package_name} not found")
            all_ok = False

    return all_ok


def test_env_file():
    """Test if .env file exists and is configured"""
    print("\n" + "=" * 60)
    print("Testing Environment Configuration")
    print("=" * 60)

    if not os.path.exists(".env"):
        print_error(".env file not found")
        print_info("Run: uv run python setup.py")
        return False

    print_success(".env file exists")

    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    if provider in ("openai", "ollama", "omlx", "mlx"):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        if api_key and api_key != "your_openai_api_key_here" and base_url:
            print_success(f"OpenAI-compatible provider configured: {base_url}")
        else:
            print_error("OPENAI_API_KEY or OPENAI_BASE_URL not configured")
            return False
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
        if api_key and api_key != "your_anthropic_api_key_here":
            print_success("Anthropic provider is configured")
        else:
            print_error("ANTHROPIC_API_KEY not configured")
            print_info("Edit .env and add your Anthropic API key")
            return False

    demo_usdc = os.getenv("DEMO_USDC_BALANCE", "10.0")
    print_success(
        f"Temporary in-memory wallet enabled ({demo_usdc} simulated USDC)"
    )

    return True


def main():
    print(f"\n{Fore.CYAN}{'=' * 60}")
    print("x402 Agent Demo - System Test")
    print(f"{'=' * 60}{Style.RESET_ALL}\n")

    results = []

    # Test dependencies
    results.append(("Dependencies", test_dependencies()))

    # Test environment
    results.append(("Environment", test_env_file()))

    # Test mock service
    results.append(("Mock Service", test_mock_service()))

    # Summary
    print(f"\n{Fore.CYAN}{'=' * 60}")
    print("Test Summary")
    print(f"{'=' * 60}{Style.RESET_ALL}\n")

    for name, result in results:
        if result:
            print_success(f"{name}: PASSED")
        else:
            print_error(f"{name}: FAILED")

    all_passed = all(r[1] for r in results)

    if all_passed:
        print(f"\n{Fore.GREEN}✓ All tests passed!{Style.RESET_ALL}")
        print(f"\n{Fore.CYAN}Ready to run the agent:{Style.RESET_ALL}")
        print("  uv run python run_agent.py")
        return 0
    else:
        print(f"\n{Fore.RED}✗ Some tests failed{Style.RESET_ALL}")
        print(
            f"{Fore.YELLOW}Please fix the issues above before running the agent{Style.RESET_ALL}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
