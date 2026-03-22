"""
Seed Script – Education Tutor
================================
Creates:
  - 1 default admin account
  - 2 sample student accounts
  - Sample FAQ cache entries

Usage:
    python seed.py
    # or inside Docker:
    docker-compose exec backend python seed.py
"""

import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


async def seed():
    from utils.db import connect_db, get_db
    from utils.auth import hash_password

    await connect_db()
    db = get_db()

    print("\n📚 Education Tutor – Seeding Database\n")

    # ── Admin account ─────────────────────────────────────────────────────────
    admin_email = os.getenv("SEED_ADMIN_EMAIL", "admin@edututor.in")
    admin_pass  = os.getenv("SEED_ADMIN_PASS",  "Admin@123")

    existing = await db.users.find_one({"email": admin_email})
    if existing:
        print(f"  ⚠️  Admin already exists: {admin_email}")
    else:
        await db.users.insert_one({
            "name": "Admin Teacher",
            "email": admin_email,
            "hashed_password": hash_password(admin_pass),
            "role": "admin",
            "language": "en",
            "created_at": datetime.utcnow(),
            "last_login": None
        })
        print(f"  ✅ Admin created:   {admin_email}  /  {admin_pass}")

    # ── Student accounts ──────────────────────────────────────────────────────
    students = [
        {"name": "Anita Sharma",   "email": "anita@student.in",  "language": "hi"},
        {"name": "Ravi Kumar",     "email": "ravi@student.in",   "language": "en"},
    ]

    for s in students:
        existing = await db.users.find_one({"email": s["email"]})
        if existing:
            print(f"  ⚠️  Student exists:  {s['email']}")
            continue
        await db.users.insert_one({
            "name": s["name"],
            "email": s["email"],
            "hashed_password": hash_password("Student@123"),
            "role": "student",
            "language": s["language"],
            "created_at": datetime.utcnow(),
            "last_login": None
        })
        print(f"  ✅ Student created: {s['email']}  /  Student@123")

    # ── Sample FAQ Cache ──────────────────────────────────────────────────────
    import hashlib, json

    faqs = [
        {
            "question": "What is photosynthesis?",
            "language": "en",
            "answer": json.dumps({
                "simple_explanation": "Photosynthesis is the process by which green plants use sunlight, water, and carbon dioxide to make their own food (glucose) and release oxygen.",
                "example": "Just like you need food to have energy, plants make their food using sunlight. A mango tree uses sunlight on its leaves to create the sugars that make the fruit sweet.",
                "summary": "Plants convert sunlight + CO₂ + water → glucose + oxygen using chlorophyll in their leaves.",
                "practice_question": "What are the three things a plant needs to perform photosynthesis?"
            })
        },
        {
            "question": "What is the Pythagorean theorem?",
            "language": "en",
            "answer": json.dumps({
                "simple_explanation": "In a right-angled triangle, the square of the longest side (hypotenuse) equals the sum of squares of the other two sides. Written as: a² + b² = c²",
                "example": "If a ladder leans against a wall, with the base 3m from the wall and reaching 4m up — the ladder length is √(3²+4²) = √25 = 5 metres.",
                "summary": "a² + b² = c² where c is the hypotenuse (the longest side, opposite the right angle).",
                "practice_question": "A right triangle has sides of 5cm and 12cm. What is the length of the hypotenuse?"
            })
        },
        {
            "question": "प्रकाश संश्लेषण क्या है?",
            "language": "hi",
            "answer": json.dumps({
                "simple_explanation": "प्रकाश संश्लेषण वह प्रक्रिया है जिसमें हरे पौधे सूर्य के प्रकाश, पानी और कार्बन डाइऑक्साइड का उपयोग करके अपना भोजन (ग्लूकोज) बनाते हैं और ऑक्सीजन छोड़ते हैं।",
                "example": "जैसे हमें ऊर्जा के लिए खाना चाहिए, वैसे ही पेड़-पौधे सूरज की रोशनी से अपना खाना खुद बनाते हैं।",
                "summary": "पौधे: सूर्य प्रकाश + CO₂ + जल → ग्लूकोज + ऑक्सीजन बनाते हैं।",
                "practice_question": "प्रकाश संश्लेषण के लिए पौधे को किन तीन चीजों की आवश्यकता होती है?"
            })
        }
    ]

    for faq in faqs:
        q_hash = hashlib.md5(f"{faq['question'].lower().strip()}:{faq['language']}".encode()).hexdigest()
        existing = await db.faq_cache.find_one({"question_hash": q_hash})
        if existing:
            print(f"  ⚠️  FAQ exists: {faq['question'][:40]}…")
            continue
        await db.faq_cache.insert_one({
            "question_hash": q_hash,
            "question": faq["question"],
            "answer": faq["answer"],
            "language": faq["language"],
            "hit_count": 0,
            "created_at": datetime.utcnow(),
            "last_accessed": datetime.utcnow()
        })
        print(f"  ✅ FAQ cached: {faq['question'][:50]}")

    print("\n✅ Seeding complete!\n")
    print("  Admin login:   admin@edututor.in   /  Admin@123")
    print("  Student login: anita@student.in    /  Student@123")
    print("  Student login: ravi@student.in     /  Student@123")
    print("\n  Next steps:")
    print("  1. Log in as admin and upload a textbook PDF")
    print("  2. Run: python setup_atlas_index.py")
    print("  3. Log in as student and ask questions!\n")


if __name__ == "__main__":
    asyncio.run(seed())
