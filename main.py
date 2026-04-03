
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from PyPDF2 import PdfReader
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, Session

STOPWORDS = {"the", "and", "of", "in", "a", "an", "is", "it", "to", "for", "on", "at", "by", "with", "this", "that", "are", "was", "be", "as", "or"}

app = FastAPI()

# =========================
# 🗄️ DATABASE SETUP
# =========================
DATABASE_URL = "sqlite:///./school.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Teacher(Base):
    __tablename__ = "teachers"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)


class Knowledge(Base):
    __tablename__ = "knowledge"
    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String)
    topic = Column(String)
    content = Column(Text)
    keywords = Column(Text)
    teacher_id = Column(Integer, ForeignKey("teachers.id"))


Base.metadata.create_all(bind=engine)


# =========================
# 🔌 DB DEPENDENCY
# =========================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# 📥 REQUEST MODELS
# =========================
class TeacherLogin(BaseModel):
    email: str


class UploadRequest(BaseModel):
    teacher_email: str
    subject: str
    topic: str
    content: str
    keywords: list[str]


class ChatRequest(BaseModel):
    message: str
    subject: str | None = None  # optional subject filter


# =========================
# 🔐 TEACHER LOGIN
# =========================
@app.post("/teacher/login")
def login(data: TeacherLogin, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.email == data.email).first()

    if not teacher:
        teacher = Teacher(email=data.email)
        db.add(teacher)
        db.commit()
        db.refresh(teacher)

    return {
        "message": "Login successful",
        "teacher_id": teacher.id
    }


# =========================
# 📚 TEACHER UPLOAD
# =========================
@app.post("/teacher/upload")
def upload_data(data: UploadRequest, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.email == data.teacher_email).first()

    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found. Please login first.")

    keywords_str = ",".join([k.lower().strip() for k in data.keywords])

    new_entry = Knowledge(
        subject=data.subject.lower(),
        topic=data.topic.lower(),
        content=data.content,
        keywords=keywords_str,
        teacher_id=teacher.id
    )

    db.add(new_entry)
    db.commit()

    return {"message": "Content uploaded successfully"}


# =========================
# 📄 PDF UPLOAD  (BUG FIXED)
# =========================
@app.post("/teacher/upload-pdf")
def upload_pdf(
    file: UploadFile = File(...),
    teacher_email: str = Form(...),       # FIX: accept teacher email, not hardcoded ID
    subject: str = Form(default="general"),
    topic: str = Form(default="pdf_content"),
    db: Session = Depends(get_db)
):
    # Validate teacher
    teacher = db.query(Teacher).filter(Teacher.email == teacher_email).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found. Please login first.")

    # Extract text from PDF
    reader = PdfReader(file.file)
    full_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"

    if not full_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from PDF.")

    # Split into word chunks
    words = full_text.split()
    chunk_size = 100
    chunks = [
        " ".join(words[i:i + chunk_size])
        for i in range(0, len(words), chunk_size)
    ]

    saved_chunks = 0

    # FIX: new_entry creation is now INSIDE the loop
    for chunk in chunks:
        chunk = chunk.strip()

        if len(chunk) < 20:
            continue

        text = chunk.lower()

        # Skip boilerplate lines
        if "module" in text or "page" in text:
            continue
        
        meaningful_words = [w for w in text.split() if w not in STOPWORDS]  


        new_entry = Knowledge(
            subject=subject.lower(),
            topic=topic.lower(),
            content=chunk,
            keywords=",".join(meaningful_words[:5]),
            teacher_id=teacher.id          # FIX: use real teacher ID
        )
        db.add(new_entry)
        saved_chunks += 1                  # FIX: increment inside loop

    db.commit()

    return {"message": f"{saved_chunks} chunks saved successfully"}


# =========================
# 🎓 STUDENT CHATBOT  (IMPROVED MATCHING)
# =========================
@app.post("/chat/learning")
def chat(request: ChatRequest, db: Session = Depends(get_db)):
    user_msg = request.message.lower()
    user_words = set(user_msg.split())

    # Optionally filter by subject
    query = db.query(Knowledge)
    if request.subject:
        query = query.filter(Knowledge.subject == request.subject.lower())

    results = query.all()

    if not results:
        return {"response": "Sorry, I don't have information on that topic yet."}

    best_match = None
    best_score = 0

    for item in results:
        keyword_list = [k.strip() for k in item.keywords.split(",") if k.strip()]
        topic_words = set(item.topic.split("_"))

        score = 0

        # Score: keyword hits
        for word in keyword_list:
            if word in user_words:
                score += 2          # exact keyword match = higher weight

        # Score: topic word hits
        for word in topic_words:
            if word in user_words:
                score += 1

        # Score: subject match bonus
        if request.subject and item.subject == request.subject.lower():
            score += 1

        if score > best_score:
            best_score = score
            best_match = item

    # Only respond if there's at least one keyword match
    if best_match and best_score > 0:
        return {
            "response": best_match.content,
            "matched_topic": best_match.topic,
            "matched_subject": best_match.subject,
            "confidence_score": best_score
        }

    return {"response": "Sorry, I don't have information on that topic yet."}


# =========================
# 🏠 HOME
# =========================
@app.get("/")
def home():
    return {"message": "School Chatbot API is running 🚀"}


@app.delete("/admin/clear-knowledge")
def clear_knowledge(db: Session = Depends(get_db)):
    db.query(Knowledge).delete()
    db.commit()
    return {"message": "All knowledge entries deleted"}