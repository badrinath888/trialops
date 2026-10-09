import os
from uuid import UUID
from mcp.server.fastmcp import FastMCP
import tools

w = UUID(os.environ["WORKSPACE_ID"])
server = FastMCP("TrialOps evidence")


@server.tool()
def search_cases(query: str):
    return {"cases": tools.search_cases(w, query)}


@server.tool()
def get_study(study_id: str):
    return {"study": tools.get_study(w, study_id)}


@server.tool()
def get_site(site_id: str):
    return {"site": tools.get_site(w, site_id)}


@server.tool()
def search_knowledge(query: str):
    return {
        "articles": tools.search_knowledge(w, query, os.getenv("AI_MODE") == "ollama")
    }


@server.tool()
def get_sync_jobs(study_id: str, site_id: str):
    return {
        "synchronization": tools.get_operations(w, study_id, site_id)["synchronization"]
    }


@server.tool()
def get_document_processing(study_id: str, site_id: str):
    return {
        "document_processing": tools.get_operations(w, study_id, site_id)[
            "document_processing"
        ]
    }


if __name__ == "__main__":
    server.run(transport="stdio")
