# backend/main.py
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.orm import Session

# Ajustado: Importando os módulos internos com o prefixo absoluto do pacote backend
from backend import database
from backend import models

# 1. Inicialização da API FastAPI
app = FastAPI(
    title="ControlTask API",
    description="Backend para gerenciamento de tarefas pessoais",
    version="1.0.0"
)

# Configuração de CORS (Permite que o Streamlit no Frontend acesse esta API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Em produção, substitua pelo endereço exato do Frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Criação Automatizada das Tabelas no SQLite
# Quando o servidor rodar, se as tabelas não existirem, o SQLAlchemy irá criá-las instantaneamente.
models.Base.metadata.create_all(bind=database.engine)

# =========================================================================
# SCHEMAS DE VALIDAÇÃO (PYDANTIC)
# =========================================================================

# Schemas para Usuário
class UserCreate(BaseModel):
    name: str
    email: EmailStr  # Utiliza o email-validator instalado nos bastidores
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str

# Schemas para Tarefa
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str # 'LOW', 'MEDIUM', 'HIGH'

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None # 'PENDING', 'IN_PROGRESS', 'COMPLETED'

class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    description: Optional[str]
    priority: str
    status: str


# =========================================================================
# ENDPOINTS / ROTAS DA API
# =========================================================================

# --- ROTAS DE USUÁRIO ---
@app.get("/", tags=["Raiz"])
def read_root():
    return {"status": "ControlTask API rodando com sucesso!", "documentacao": "/docs"}

@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Usuários"])
def create_user(user: UserCreate, db: Session = Depends(database.get_db)):
    """Cadastra um novo usuário no sistema."""
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")
    
    # IMPORTANTE: Em produção, utilize bcrypt para criptografar a senha!
    new_user = models.User(
        name=user.name,
        email=user.email,
        password_hash=user.password # Emulando o hash para fins didáticos no MVP
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


# --- CRUD DE TAREFAS ---

@app.post("/users/{user_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, tags=["Tarefas"])
def create_task(user_id: int, task: TaskCreate, db: Session = Depends(database.get_db)):
    """Cria uma nova tarefa associada a um usuário específico (CREATE)."""
    # Verifica se o usuário existe
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    
    # Validação de domínio para prioridade
    if task.priority.upper() not in ["LOW", "MEDIUM", "HIGH"]:
        raise HTTPException(status_code=400, detail="Prioridade inválida. Use LOW, MEDIUM ou HIGH.")

    new_task = models.Task(
        user_id=user_id,
        title=task.title,
        description=task.description,
        priority=task.priority.upper()
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task


@app.get("/users/{user_id}/tasks", response_model=List[TaskResponse], tags=["Tarefas"])
def read_tasks(user_id: int, db: Session = Depends(database.get_db)):
    """Lista todas as tarefas de um usuário (READ LIST)."""
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    tasks = db.query(models.Task).filter(models.Task.user_id == user_id).all()
    return tasks


@app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Tarefas"])
def read_single_task(task_id: int, db: Session = Depends(database.get_db)):
    """Busca os detalhes de uma única tarefa pelo ID (READ SPECIFIC)."""
    db_task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return db_task


@app.put("/tasks/{task_id}", response_model=TaskResponse, tags=["Tarefas"])
def update_task(task_id: int, task_data: TaskUpdate, db: Session = Depends(database.get_db)):
    """Atualiza qualquer atributo ou status de uma tarefa existente (UPDATE)."""
    db_task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    
    # Atualiza apenas os campos que foram enviados na requisição
    update_dict = task_data.model_dump(exclude_unset=True)
    
    if "priority" in update_dict and update_dict["priority"].upper() not in ["LOW", "MEDIUM", "HIGH"]:
        raise HTTPException(status_code=400, detail="Prioridade inválida.")
    if "status" in update_dict and update_dict["status"].upper() not in ["PENDING", "IN_PROGRESS", "COMPLETED"]:
        raise HTTPException(status_code=400, detail="Status inválido.")

    for key, value in update_dict.items():
        if key in ["priority", "status"]:
            setattr(db_task, key, value.upper())
        else:
            setattr(db_task, key, value)

    db.commit()
    db.refresh(db_task)
    return db_task


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tarefas"])
def delete_task(task_id: int, db: Session = Depends(database.get_db)):
    """Remove definitivamente uma tarefa do banco de dados (DELETE)."""
    db_task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    
    db.delete(db_task)
    db.commit()
    return None
