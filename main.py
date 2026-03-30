from fastapi import FastAPI
from fastapi import UploadFile, File
from pyPDF2 import pdfReader
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base

app = FastAPI()

# =========================
# 🗄️ DATABASE SETUP
# =========================
DATABASE_URL = "sqlite:///./school.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# =========================
# 📚 MODELS
# =========================
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

# Create tables
Base.metadata.create_all(bind=engine)

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

# =========================
# 🔐 TEACHER LOGIN
# =========================
@app.post("/teacher/login")
def login(data: TeacherLogin):
    db = SessionLocal()

    teacher = db.query(Teacher).filter(Teacher.email == data.email).first()

    if not teacher:
        teacher = Teacher(email=data.email)
        db.add(teacher)
        db.commit()
        db.refresh(teacher)

    db.close()

    return {
        "message": "Login successful",
        "teacher_id": teacher.id
    }

# =========================
# 📚 TEACHER UPLOAD
# =========================
@app.post("/teacher/upload")
def upload_data(data: UploadRequest):
    db = SessionLocal()

    teacher = db.query(Teacher).filter(Teacher.email == data.teacher_email).first()

    if not teacher:
        db.close()
        return {"error": "Teacher not found. Please login first."}

    keywords_str = ",".join([k.lower() for k in data.keywords])

    new_entry = Knowledge(
        subject=data.subject.lower(),
        topic=data.topic.lower(),
        content=data.content,
        keywords=keywords_str,
        teacher_id=teacher.id
    )

    db.add(new_entry)
    db.commit()
    db.close()

    return {"message": "Content uploaded successfully"}

# =========================
# 📄 PDF UPLOAD
# =========================
@app.post("/teacher/upload-pdf")
def upload_pdf(file: UploadFile = File(...)):
    db = SessionLocal()

    reader = PdfReader(file.file)
    full_text = ""

    for page in reader.pages:
        full_text += page.extract_text() + "\n"

    chunks = full_text.split("\n")

    saved_chunks = 0

    for chunk in chunks:
        chunk = chunk.strip()

        if len(chunk) < 50:
            continue

        new_entry = Knowledge(
            subject="general",
            topic="pdf_content",
            content=chunk,
            keywords=",".join(chunk.lower().split()[:5]),
            teacher_id=1
        )

        db.add(new_entry)
        saved_chunks += 1

    db.commit()
    db.close()

    return {
        "message": f"{saved_chunks} chunks saved successfully"
    }
# =========================
# 🎓 STUDENT CHATBOT
# =========================
@app.post("/chat/learning")
def chat(request: ChatRequest):
    db = SessionLocal()
    user_msg = request.message.lower()

    results = db.query(Knowledge).all()

    for item in results:
        keyword_list = item.keywords.split(",")

        # Match topic
        if item.topic in user_msg:
            db.close()
            return {"response": item.content}

        # Match keywords
        for word in keyword_list:
            if word in user_msg:
                db.close()
                return {"response": item.content}

    db.close()
    return {
        "response": "Sorry, I don’t have information on that topic yet."
    }

# =========================
# 🏠 HOME
# =========================
@app.get("/")
def home():
    return {"message": "Full chatbot system is running 🚀"}