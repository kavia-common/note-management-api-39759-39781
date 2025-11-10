from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Path, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

# PUBLIC_INTERFACE
class NoteBase(BaseModel):
    """Base fields for creating or updating a note."""
    title: str = Field(..., description="Title of the note")
    content: Optional[str] = Field(None, description="Content of the note (optional)")

    @field_validator("title")
    @classmethod
    def validate_title_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("title must be a non-empty string")
        return v.strip()


# PUBLIC_INTERFACE
class NoteCreate(NoteBase):
    """Schema for creating a new note."""
    pass


# PUBLIC_INTERFACE
class NoteUpdate(BaseModel):
    """Schema for updating an existing note."""
    title: Optional[str] = Field(None, description="Updated title of the note")
    content: Optional[str] = Field(None, description="Updated content of the note (optional)")

    @field_validator("title")
    @classmethod
    def validate_title_if_present(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not isinstance(v, str) or not v.strip():
            raise ValueError("title must be a non-empty string when provided")
        return v.strip()


# PUBLIC_INTERFACE
class Note(NoteBase):
    """Note schema including identifiers and timestamps."""
    id: UUID = Field(..., description="Unique identifier for the note")
    created_at: datetime = Field(..., description="Creation timestamp in UTC")
    updated_at: datetime = Field(..., description="Last update timestamp in UTC")


# Service abstraction with in-memory persistence for now.
class NotesService:
    """Service layer for managing notes. Uses an in-memory store; can be swapped out with a DB implementation later."""
    def __init__(self) -> None:
        # Using a dict[UUID, Note] as the in-memory store
        self._store: Dict[UUID, Note] = {}

    # PUBLIC_INTERFACE
    def create(self, payload: NoteCreate) -> Note:
        """Create a new note from the provided payload."""
        now = datetime.utcnow()
        note = Note(id=uuid4(), title=payload.title, content=payload.content, created_at=now, updated_at=now)
        self._store[note.id] = note
        return note

    # PUBLIC_INTERFACE
    def list(self) -> List[Note]:
        """List all notes."""
        return list(self._store.values())

    # PUBLIC_INTERFACE
    def get(self, note_id: UUID) -> Note:
        """Retrieve a single note by ID."""
        note = self._store.get(note_id)
        if not note:
            raise KeyError("not_found")
        return note

    # PUBLIC_INTERFACE
    def update(self, note_id: UUID, payload: NoteUpdate) -> Note:
        """Update an existing note by ID with provided fields."""
        note = self._store.get(note_id)
        if not note:
            raise KeyError("not_found")

        data = note.model_dump()
        if payload.title is not None:
            data["title"] = payload.title
        if payload.content is not None:
            data["content"] = payload.content
        data["updated_at"] = datetime.utcnow()
        updated = Note(**data)
        self._store[note_id] = updated
        return updated

    # PUBLIC_INTERFACE
    def delete(self, note_id: UUID) -> None:
        """Delete a note by ID."""
        if note_id not in self._store:
            raise KeyError("not_found")
        del self._store[note_id]


# Initialize FastAPI app with metadata and CORS
app = FastAPI(
    title="Notes Management API",
    description="A simple FastAPI service providing CRUD operations for notes.",
    version="1.0.0",
    openapi_tags=[
        {"name": "Health", "description": "Service health endpoints"},
        {"name": "Notes", "description": "CRUD operations for notes"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to known front-end origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a singleton service instance for the app lifetime
notes_service = NotesService()


@app.get(
    "/health",
    summary="Health Check",
    description="Returns basic health status for the service.",
    tags=["Health"],
    response_model=dict,
    responses={
        200: {"description": "Service is healthy", "content": {"application/json": {"example": {"status": "ok"}}}}
    },
)
# PUBLIC_INTERFACE
def health_check() -> dict:
    """Health check endpoint.
    Returns a simple JSON indicating that the service is operational.

    Returns:
        dict: An object with status set to 'ok'
    """
    return {"status": "ok"}


@app.post(
    "/notes",
    summary="Create Note",
    description="Create a new note with a non-empty title and optional content.",
    tags=["Notes"],
    response_model=Note,
    status_code=status.HTTP_201_CREATED,
)
# PUBLIC_INTERFACE
def create_note(payload: NoteCreate) -> Note:
    """Create a new note.
    Parameters:
        payload (NoteCreate): The note creation payload containing a non-empty title and optional content.
    Returns:
        Note: The created note including id and timestamps.
    """
    return notes_service.create(payload)


@app.get(
    "/notes",
    summary="List Notes",
    description="List all notes currently stored by the service.",
    tags=["Notes"],
    response_model=List[Note],
)
# PUBLIC_INTERFACE
def list_notes() -> List[Note]:
    """List all notes.
    Returns:
        List[Note]: A list of notes.
    """
    return notes_service.list()


@app.get(
    "/notes/{note_id}",
    summary="Get Note",
    description="Retrieve a single note by its ID.",
    tags=["Notes"],
    response_model=Note,
    responses={404: {"description": "Note not found"}},
)
# PUBLIC_INTERFACE
def get_note(
    note_id: UUID = Path(..., description="The UUID of the note to retrieve"),
) -> Note:
    """Retrieve a note by ID.
    Parameters:
        note_id (UUID): The UUID of the desired note.
    Returns:
        Note: The requested note.
    Raises:
        HTTPException(404): If the note does not exist.
    """
    try:
        return notes_service.get(note_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")


@app.put(
    "/notes/{note_id}",
    summary="Update Note",
    description="Update fields of an existing note. Title, if provided, must be non-empty.",
    tags=["Notes"],
    response_model=Note,
    responses={404: {"description": "Note not found"}},
)
# PUBLIC_INTERFACE
def update_note(
    note_id: UUID = Path(..., description="The UUID of the note to update"),
    payload: NoteUpdate = ...,
) -> Note:
    """Update an existing note.
    Parameters:
        note_id (UUID): The UUID of the note to update.
        payload (NoteUpdate): Fields to update (title and/or content).
    Returns:
        Note: The updated note.
    Raises:
        HTTPException(404): If the note does not exist.
    """
    try:
        return notes_service.update(note_id, payload)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")


@app.delete(
    "/notes/{note_id}",
    summary="Delete Note",
    description="Delete a note by its ID.",
    tags=["Notes"],
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Note not found"}, 204: {"description": "Deleted"}},
)
# PUBLIC_INTERFACE
def delete_note(note_id: UUID = Path(..., description="The UUID of the note to delete")) -> None:
    """Delete a note by ID.
    Parameters:
        note_id (UUID): The UUID of the note to delete.
    Raises:
        HTTPException(404): If the note does not exist.
    """
    try:
        notes_service.delete(note_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
