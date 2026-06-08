"""
Mock x402 Service - Simulates paid content APIs
Returns HTTP 402 when payment is required
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import hashlib
import json
import os
from typing import Dict, Optional

app = Flask(__name__)
CORS(app)

# Simulated payment database (in production, this would be blockchain verification)
paid_requests: Dict[str, dict] = {}

# Service pricing
SERVICES = {
    "premium_article": {
        "price": 0.5,  # USDC
        "currency": "USDC",
        "description": "Premium Research Article on Quantum Computing",
    },
    "image_generation": {
        "price": 0.8,
        "currency": "USDC",
        "description": "AI-Generated 4K Image",
    },
    "video_generation": {
        "price": 5.0,
        "currency": "USDC",
        "description": "AI-Generated 10s 4K Video",
    },
}

# Merchant wallet address (simulated)
MERCHANT_ADDRESS = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"


def generate_challenge(service_id: str) -> str:
    """Generate a unique challenge for payment verification"""
    timestamp = str(int(time.time()))
    data = f"{service_id}:{timestamp}:{MERCHANT_ADDRESS}"
    return hashlib.sha256(data.encode()).hexdigest()


def verify_payment(tx_hash: Optional[str], service_id: str) -> bool:
    """
    Verify payment on blockchain (simulated)
    In production, this would call Web3 to verify the actual transaction
    """
    # For demo purposes, we accept any non-empty tx_hash
    # In production: verify tx on blockchain, check amount, recipient, etc.
    if not tx_hash:
        return False
    return len(tx_hash) > 10


@app.route("/api/article/<article_id>", methods=["GET"])
def get_article(article_id):
    """Premium article endpoint - requires payment"""

    # Check if payment proof is provided
    payment_proof = request.headers.get("X-Payment-Proof")

    if payment_proof:
        # Verify payment
        try:
            proof_data = json.loads(payment_proof)
            tx_hash = proof_data.get("tx_hash")

            if verify_payment(tx_hash, f"article_{article_id}"):
                # Payment verified, return content
                return jsonify(
                    {
                        "id": article_id,
                        "title": "Quantum Computing: Latest Breakthroughs in 2026",
                        "content": "This is premium research content about quantum computing advances...",
                        "author": "Dr. Alice Quantum",
                        "published": "2026-01-22",
                        "paid": True,
                    }
                ), 200
        except Exception as e:
            pass

    # No payment or invalid payment - return 402
    service = SERVICES["premium_article"]
    challenge = generate_challenge(f"article_{article_id}")

    response = jsonify(
        {
            "error": "payment_required",
            "message": "This is premium content. Payment required.",
            "service": "premium_article",
        }
    )

    # Add x402 payment headers
    response.headers["X-Payment-Required"] = "true"
    response.headers["X-Payment-Amount"] = str(service["price"])
    response.headers["X-Payment-Currency"] = service["currency"]
    response.headers["X-Payment-Address"] = MERCHANT_ADDRESS
    response.headers["X-Payment-Challenge"] = challenge
    response.headers["X-Payment-Description"] = service["description"]

    return response, 402


@app.route("/api/generate/image", methods=["POST"])
def generate_image():
    """AI Image generation endpoint - requires payment"""

    payment_proof = request.headers.get("X-Payment-Proof")

    if payment_proof:
        try:
            proof_data = json.loads(payment_proof)
            tx_hash = proof_data.get("tx_hash")

            if verify_payment(tx_hash, "image_gen"):
                # Payment verified, return generated image URL
                prompt = request.json.get("prompt", "cyberpunk city")
                return jsonify(
                    {
                        "status": "success",
                        "image_url": f"https://example.com/generated/{hashlib.md5(prompt.encode()).hexdigest()}.png",
                        "prompt": prompt,
                        "paid": True,
                    }
                ), 200
        except Exception as e:
            pass

    # Payment required
    service = SERVICES["image_generation"]
    challenge = generate_challenge("image_gen")

    response = jsonify(
        {
            "error": "payment_required",
            "message": "AI image generation requires payment.",
            "service": "image_generation",
        }
    )

    response.headers["X-Payment-Required"] = "true"
    response.headers["X-Payment-Amount"] = str(service["price"])
    response.headers["X-Payment-Currency"] = service["currency"]
    response.headers["X-Payment-Address"] = MERCHANT_ADDRESS
    response.headers["X-Payment-Challenge"] = challenge
    response.headers["X-Payment-Description"] = service["description"]

    return response, 402


@app.route("/api/generate/video", methods=["POST"])
def generate_video():
    """AI Video generation endpoint - requires payment (high cost)"""

    payment_proof = request.headers.get("X-Payment-Proof")

    if payment_proof:
        try:
            proof_data = json.loads(payment_proof)
            tx_hash = proof_data.get("tx_hash")

            if verify_payment(tx_hash, "video_gen"):
                prompt = request.json.get("prompt", "4K landscape")
                return jsonify(
                    {
                        "status": "success",
                        "video_url": f"https://example.com/generated/{hashlib.md5(prompt.encode()).hexdigest()}.mp4",
                        "prompt": prompt,
                        "duration": "10s",
                        "resolution": "4K",
                        "paid": True,
                    }
                ), 200
        except Exception as e:
            pass

    service = SERVICES["video_generation"]
    challenge = generate_challenge("video_gen")

    response = jsonify(
        {
            "error": "payment_required",
            "message": "AI video generation requires payment.",
            "service": "video_generation",
        }
    )

    response.headers["X-Payment-Required"] = "true"
    response.headers["X-Payment-Amount"] = str(service["price"])
    response.headers["X-Payment-Currency"] = service["currency"]
    response.headers["X-Payment-Address"] = MERCHANT_ADDRESS
    response.headers["X-Payment-Challenge"] = challenge
    response.headers["X-Payment-Description"] = service["description"]

    return response, 402


@app.route("/api/services", methods=["GET"])
def list_services():
    """List all available paid services and their pricing"""
    port = os.getenv("MOCK_SERVICE_PORT", "5000")
    base = f"http://localhost:{port}"
    return jsonify(
        {
            "services": [
                {
                    "name": "premium_article",
                    "description": SERVICES["premium_article"]["description"],
                    "price": SERVICES["premium_article"]["price"],
                    "currency": SERVICES["premium_article"]["currency"],
                    "method": "GET",
                    "endpoint": f"{base}/api/article/<article_id>",
                    "example_ids": [
                        "quantum-2026",
                        "blockchain-privacy",
                        "ai-agent-survey",
                    ],
                },
                {
                    "name": "image_generation",
                    "description": SERVICES["image_generation"]["description"],
                    "price": SERVICES["image_generation"]["price"],
                    "currency": SERVICES["image_generation"]["currency"],
                    "method": "POST",
                    "endpoint": f"{base}/api/generate/image",
                    "body": {"prompt": "your image description"},
                },
                {
                    "name": "video_generation",
                    "description": SERVICES["video_generation"]["description"],
                    "price": SERVICES["video_generation"]["price"],
                    "currency": SERVICES["video_generation"]["currency"],
                    "method": "POST",
                    "endpoint": f"{base}/api/generate/video",
                    "body": {"prompt": "your video description"},
                },
            ],
            "merchant_address": MERCHANT_ADDRESS,
            "note": "All endpoints return HTTP 402 without valid payment proof.",
        }
    ), 200


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify(
        {"status": "healthy", "service": "x402-mock-service", "version": "0.1.0"}
    ), 200


if __name__ == "__main__":
    port = int(os.getenv("MOCK_SERVICE_PORT", "5000"))
    print(f"🚀 Starting x402 Mock Service on http://localhost:{port}")
    print("Available endpoints:")
    print("  GET  /api/services          - List all paid services (free)")
    print("  GET  /api/article/<id>      - Premium article (0.5 USDC)")
    print("  POST /api/generate/image    - AI image (0.8 USDC)")
    print("  POST /api/generate/video    - AI video (5.0 USDC)")
    app.run(host="0.0.0.0", port=port, debug=True)
