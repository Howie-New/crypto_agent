#!/usr/bin/env python3
"""
Quick start script for x402 Agent Demo
Creates a local demo configuration file
"""

import os


def create_env_file():
    """Create a local .env file from the safe demo template."""

    if os.path.exists(".env"):
        print(
            "⚠️  .env file already exists. Please edit it manually or delete it first."
        )
        return

    # Read .env.example
    with open(".env.example", "r") as f:
        env_template = f.read()

    env_content = env_template.replace("your_anthropic_api_key_here", "")

    # Write .env
    with open(".env", "w") as f:
        f.write(env_content)

    print("\n✅ Created .env file")
    print("\n📝 Next steps:")
    print("1. Edit .env and add your ANTHROPIC_API_KEY")
    print("   Get one at: https://console.anthropic.com/")
    print("2. Run 'uv run python run_mock_service.py' to start the mock service")
    print("3. Run 'uv run python run_agent.py' to start the agent")
    print("4. Optional: configure Telegram values and run 'uv run python telegram_bot.py'")


if __name__ == "__main__":
    create_env_file()
