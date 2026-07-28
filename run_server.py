"""Simple script to run the server."""

if __name__ == "__main__":
    import uvicorn
    from app.utils.config import get_settings
    
    settings = get_settings()
    print(f"Starting Vera AI Decision Engine v{settings.version}")
    print(f"Server: {settings.host}:{settings.port}")
    print(f"Team: {settings.team_name}")
    print(f"Log level: {settings.log_level}")
    print("-" * 50)
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
