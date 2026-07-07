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

ARTICLE_CATALOG = {
    "quantum-2026": {
        "title": "Quantum Computing: Latest Breakthroughs in 2026",
        "author": "Dr. Alice Quantum",
        "published": "2026-01-22",
        "deck": (
            "A practical briefing on why quantum hardware progress matters, "
            "where error correction stands, and what teams should do before "
            "cryptographically relevant quantum machines arrive."
        ),
        "sections": [
            {
                "heading": "Executive take",
                "body": (
                    "Quantum computing is moving from headline qubit counts toward "
                    "engineering metrics that matter: lower logical error rates, "
                    "repeatable calibration, faster decoding, and clearer application "
                    "benchmarks. The most important shift is that error correction is "
                    "now being treated as the center of the system, not a future add-on."
                ),
            },
            {
                "heading": "What changed",
                "body": (
                    "Google's Willow results put renewed attention on below-threshold "
                    "surface-code behavior: larger encoded arrays reduced logical error "
                    "rates instead of amplifying them. That does not mean a useful "
                    "fault-tolerant quantum computer is finished, but it is the kind of "
                    "evidence buyers and researchers look for when separating scalable "
                    "architectures from laboratory demonstrations."
                ),
            },
            {
                "heading": "Why it matters commercially",
                "body": (
                    "Near-term quantum value is still concentrated in research workflows: "
                    "chemistry simulation, materials search, optimization experiments, "
                    "and algorithm development. The immediate enterprise action is not "
                    "'replace classical infrastructure'; it is to build a portfolio of "
                    "quantum-ready problems, data pipelines, and security migration plans."
                ),
            },
            {
                "heading": "Security impact",
                "body": (
                    "The cryptographic risk is easier to act on than the application "
                    "upside. NIST has finalized the first post-quantum cryptography "
                    "standards, including ML-KEM for key establishment and ML-DSA/SLH-DSA "
                    "for signatures. Organizations with long-lived secrets should start "
                    "inventorying vulnerable protocols and planning hybrid migration."
                ),
            },
            {
                "heading": "2026 watch list",
                "body": (
                    "The key indicators for the next wave are logical qubit lifetime, "
                    "cost per logical operation, decoder latency, cryogenic control "
                    "density, and whether application benchmarks move beyond random "
                    "circuit sampling into tasks with clear scientific or commercial value."
                ),
            },
        ],
        "sources": [
            {
                "title": "Google: Meet Willow, our state-of-the-art quantum chip",
                "url": "https://blog.google/innovation-and-ai/technology/research/google-willow-quantum-chip/",
            },
            {
                "title": "NIST: First finalized post-quantum encryption standards",
                "url": "https://www.nist.gov/news-events/news/2024/08/nist-releases-first-3-finalized-post-quantum-encryption-standards",
            },
        ],
        "assets": [
            {
                "type": "reference_video",
                "title": "Google Willow announcement media",
                "url": "https://blog.google/innovation-and-ai/technology/research/google-willow-quantum-chip/",
            }
        ],
    },
    "blockchain-privacy": {
        "title": "Blockchain Privacy in 2026: From Optional Mixers to Proof-Carrying Apps",
        "author": "Maya ZK",
        "published": "2026-02-14",
        "deck": (
            "A market map for zero-knowledge privacy, selective disclosure, "
            "compliance-friendly wallets, and private application design."
        ),
        "sections": [
            {
                "heading": "Executive take",
                "body": (
                    "Public blockchains are transparent by default, which is useful for "
                    "auditability but weak for personal privacy and business confidentiality. "
                    "The design center is shifting toward proofs that reveal only the claim "
                    "a user needs to prove, not the underlying account history or identity data."
                ),
            },
            {
                "heading": "Zero knowledge as product infrastructure",
                "body": (
                    "Zero-knowledge proofs let a prover convince a verifier that a statement "
                    "is valid without exposing the private witness behind that statement. In "
                    "consumer crypto, that can mean proving eligibility, solvency, membership, "
                    "or transaction validity while keeping sensitive attributes hidden."
                ),
            },
            {
                "heading": "The compliance trade-off",
                "body": (
                    "The privacy stack is moving away from all-or-nothing anonymity. More "
                    "teams are exploring view keys, audit keys, proof-of-innocence patterns, "
                    "rate limits, and policy proofs so that users can preserve privacy while "
                    "institutions still satisfy risk controls."
                ),
            },
            {
                "heading": "Where builders should focus",
                "body": (
                    "The most promising application patterns are private identity checks, "
                    "confidential business payments, sealed-bid auctions, private DAO voting, "
                    "and account abstraction wallets that hide operational metadata by default."
                ),
            },
            {
                "heading": "Open risks",
                "body": (
                    "Proof systems still add engineering complexity. Teams need to model "
                    "trusted setup assumptions, prover cost, mobile latency, metadata leaks, "
                    "bridge risks, and the operational burden of rotating circuits over time."
                ),
            },
        ],
        "sources": [
            {
                "title": "ethereum.org: Zero-knowledge proofs",
                "url": "https://ethereum.org/zero-knowledge-proofs/",
            },
            {
                "title": "Privacy and Scaling Explorations",
                "url": "https://pse.dev/",
            },
        ],
        "assets": [
            {
                "type": "reference_site",
                "title": "Ethereum zero-knowledge proof guide",
                "url": "https://ethereum.org/zero-knowledge-proofs/",
            }
        ],
    },
    "ai-agent-survey": {
        "title": "AI Agent Survey: Architecture Patterns That Survived the Hype",
        "author": "Lin Toolformer",
        "published": "2026-03-08",
        "deck": (
            "A builder-focused survey of LLM agents covering planning, memory, "
            "tool use, evaluation, and production failure modes."
        ),
        "sections": [
            {
                "heading": "Executive take",
                "body": (
                    "The durable pattern for LLM agents is not a single giant prompt. It is "
                    "a loop that separates task understanding, tool selection, execution, "
                    "state tracking, and verification. Systems that expose each step are "
                    "easier to debug and safer to automate."
                ),
            },
            {
                "heading": "Core architecture",
                "body": (
                    "Most useful agents combine a language model, a tool registry, a short-term "
                    "working memory, optional long-term retrieval, and a controller that limits "
                    "tool rounds. The controller is as important as the model because it decides "
                    "when to continue, stop, ask for approval, or recover from a failed action."
                ),
            },
            {
                "heading": "Planning and reflection",
                "body": (
                    "Planning helps when tasks are long or require external state, but plans "
                    "become stale quickly. Strong implementations make plans cheap to revise "
                    "and attach verification to concrete observations, not to the model's "
                    "confidence in its own reasoning."
                ),
            },
            {
                "heading": "Tool use",
                "body": (
                    "Tool schemas should be narrow, typed, and auditable. Agents become more "
                    "reliable when tools return structured data, explicit error states, and "
                    "small result sets instead of dumping unbounded text back into context."
                ),
            },
            {
                "heading": "Evaluation",
                "body": (
                    "Agent evaluation needs scenario tests, transcript review, cost tracking, "
                    "and regression fixtures for tool failures. A pass/fail final answer is "
                    "not enough; teams need to inspect whether the agent took acceptable "
                    "actions on the way to that answer."
                ),
            },
        ],
        "sources": [
            {
                "title": "A Survey on Large Language Model based Autonomous Agents",
                "url": "https://arxiv.org/abs/2308.11432",
            },
            {
                "title": "Model Context Protocol",
                "url": "https://modelcontextprotocol.io/",
            },
        ],
        "assets": [
            {
                "type": "paper",
                "title": "LLM-based autonomous agents survey",
                "url": "https://arxiv.org/abs/2308.11432",
            }
        ],
    },
}

DEFAULT_ARTICLE_ID = "quantum-2026"


def article_to_markdown(article: dict) -> str:
    """Render article data into a model-friendly Markdown body."""
    lines = [
        f"# {article['title']}",
        "",
        f"Author: {article['author']}",
        f"Published: {article['published']}",
        "",
        f"## Summary\n{article['deck']}",
    ]
    for section in article["sections"]:
        lines.extend(["", f"## {section['heading']}", section["body"]])
    lines.append("")
    lines.append("## Sources")
    for source in article["sources"]:
        lines.append(f"- {source['title']}: {source['url']}")
    return "\n".join(lines)


def get_article_payload(article_id: str) -> dict:
    article = ARTICLE_CATALOG.get(article_id, ARTICLE_CATALOG[DEFAULT_ARTICLE_ID])
    body_markdown = article_to_markdown(article)
    return {
        "id": article_id,
        "canonical_id": article_id if article_id in ARTICLE_CATALOG else DEFAULT_ARTICLE_ID,
        "title": article["title"],
        "content": body_markdown,
        "body_markdown": body_markdown,
        "summary": article["deck"],
        "sections": article["sections"],
        "sources": article["sources"],
        "assets": article["assets"],
        "author": article["author"],
        "published": article["published"],
        "paid": True,
    }


IMAGE_STYLE_PRESETS = {
    "cyberpunk": {
        "style": "cinematic cyberpunk city, neon rain, high contrast",
        "palette": ["electric cyan", "magenta", "deep black", "sodium orange"],
    },
    "quantum": {
        "style": "editorial science illustration, quantum chip, cryogenic lab",
        "palette": ["graphite", "silver", "blue", "white"],
    },
    "default": {
        "style": "polished editorial technology visual",
        "palette": ["blue", "white", "black", "green"],
    },
}

DEMO_VIDEO_ASSET = {
    "video_url": "https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    "thumbnail_url": "https://storage.googleapis.com/gtv-videos-bucket/sample/images/BigBuckBunny.jpg",
    "license_note": (
        "Demo render asset based on the open movie Big Buck Bunny. "
        "This mock endpoint does not perform real video generation."
    ),
    "source_url": "https://en.wikipedia.org/wiki/Big_Buck_Bunny",
}


def select_image_preset(prompt: str) -> dict:
    normalized = prompt.lower()
    if "cyberpunk" in normalized or "neon" in normalized:
        return IMAGE_STYLE_PRESETS["cyberpunk"]
    if "quantum" in normalized or "chip" in normalized:
        return IMAGE_STYLE_PRESETS["quantum"]
    return IMAGE_STYLE_PRESETS["default"]


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
                return jsonify(get_article_payload(article_id)), 200
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
                prompt = (request.get_json(silent=True) or {}).get(
                    "prompt", "cyberpunk city"
                )
                digest = hashlib.md5(prompt.encode()).hexdigest()
                preset = select_image_preset(prompt)
                return jsonify(
                    {
                        "status": "success",
                        "id": f"img_{digest[:12]}",
                        "image_url": f"https://picsum.photos/seed/{digest}/1536/1024.jpg",
                        "preview_url": f"https://picsum.photos/seed/{digest}/768/512.jpg",
                        "prompt": prompt,
                        "revised_prompt": f"{prompt}, {preset['style']}",
                        "style": preset["style"],
                        "palette": preset["palette"],
                        "resolution": "1536x1024",
                        "format": "jpg",
                        "mock_notice": (
                            "This is a deterministic demo image URL for the paid "
                            "workflow; no real image model was called."
                        ),
                        "source": {
                            "name": "Lorem Picsum seeded image service",
                            "url": "https://picsum.photos/",
                        },
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
                prompt = (request.get_json(silent=True) or {}).get(
                    "prompt", "4K landscape"
                )
                digest = hashlib.md5(prompt.encode()).hexdigest()
                return jsonify(
                    {
                        "status": "success",
                        "id": f"vid_{digest[:12]}",
                        "video_url": DEMO_VIDEO_ASSET["video_url"],
                        "thumbnail_url": DEMO_VIDEO_ASSET["thumbnail_url"],
                        "prompt": prompt,
                        "revised_prompt": (
                            f"{prompt}, cinematic camera move, 4K render, "
                            "10 second product-demo cut"
                        ),
                        "duration": "10s",
                        "resolution": "4K",
                        "format": "mp4",
                        "storyboard": [
                            "0-2s: Establishing shot introduces the scene.",
                            "2-6s: Camera pushes toward the main subject with motion parallax.",
                            "6-9s: Detail shot highlights texture, light, and atmosphere.",
                            "9-10s: Final hold frame suitable for a product preview.",
                        ],
                        "mock_notice": (
                            "This endpoint returns a reusable open demo video asset. "
                            "It simulates a paid generated-video response without "
                            "running a real video model."
                        ),
                        "source": {
                            "name": "Big Buck Bunny open movie sample",
                            "url": DEMO_VIDEO_ASSET["source_url"],
                            "license_note": DEMO_VIDEO_ASSET["license_note"],
                        },
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
                    "paid_response": {
                        "fields": [
                            "id",
                            "title",
                            "summary",
                            "body_markdown",
                            "sections",
                            "sources",
                            "assets",
                        ],
                        "note": "Each example ID returns a different full mock article after payment.",
                    },
                },
                {
                    "name": "image_generation",
                    "description": SERVICES["image_generation"]["description"],
                    "price": SERVICES["image_generation"]["price"],
                    "currency": SERVICES["image_generation"]["currency"],
                    "method": "POST",
                    "endpoint": f"{base}/api/generate/image",
                    "body": {"prompt": "your image description"},
                    "paid_response": {
                        "fields": [
                            "image_url",
                            "preview_url",
                            "revised_prompt",
                            "style",
                            "palette",
                            "source",
                        ],
                        "note": "Returns deterministic demo image assets for presentation.",
                    },
                },
                {
                    "name": "video_generation",
                    "description": SERVICES["video_generation"]["description"],
                    "price": SERVICES["video_generation"]["price"],
                    "currency": SERVICES["video_generation"]["currency"],
                    "method": "POST",
                    "endpoint": f"{base}/api/generate/video",
                    "body": {"prompt": "your video description"},
                    "paid_response": {
                        "fields": [
                            "video_url",
                            "thumbnail_url",
                            "revised_prompt",
                            "storyboard",
                            "source",
                        ],
                        "note": "Returns an open demo MP4 plus generation metadata.",
                    },
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
