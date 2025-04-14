# app/manage.py
import typer
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import subprocess
import sys

from app.database.base import engine
from app.database.models import Base
from app.routes import (
    auth,
    board_games,
    game_rooms,
    game_room_ws,
    game_rooms_ws,
    chat_messages,
)
from app.config import settings
from app.middleware.auth import AuthMiddleware

# Create CLI app for database and server management
cli = typer.Typer()
app = FastAPI(title="Board Game Backend")

# CORS Middleware Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Add Authentication Middleware
app.add_middleware(AuthMiddleware)

# Database and Application Setup
Base.metadata.create_all(bind=engine)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["authentication"])
app.include_router(board_games.router)
app.include_router(game_rooms.router)
app.include_router(game_rooms_ws.router)
app.include_router(game_room_ws.router)
app.include_router(chat_messages.router)


@cli.command()
def runserver(
        host: str = settings.HOST,
        port: int = settings.PORT,
        reload: bool = settings.RELOAD,
):
    """Run the FastAPI development server"""
    uvicorn.run(
        "manage:app",
        host=host,
        port=port,
        reload=reload
    )


# TODO: fixme
@cli.command()
def createmigration(
        message: str = typer.Option(..., help="Migration message describing the changes")
):
    """Create a new database migration"""
    try:
        # Ensure we're in the correct directory for running Alembic
        subprocess.run([
            "alembic",
            "revision",
            "--autogenerate",
            "-m",
            message
        ], check=True)
        typer.echo(f"Migration created for: {message}")
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error creating migration: {e}")
        sys.exit(1)


@cli.command()
def migrate():
    """Apply all pending database migrations"""
    try:
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        typer.echo("Database migrations applied successfully")
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error applying migrations: {e}")
        sys.exit(1)


@cli.command()
def rollback(
        revision: Optional[str] = typer.Option(None, help="Specific revision to roll back to")
):
    """Rollback database migrations"""
    try:
        cmd = ["alembic", "downgrade"]
        if revision:
            cmd.append(revision)
        else:
            cmd.append("-1")  # Roll back last migration by default

        subprocess.run(cmd, check=True)
        typer.echo("Database migration rolled back successfully")
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error rolling back migration: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()