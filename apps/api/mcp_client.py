import asyncio, json, os, sys, time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from db import secret


async def collect(w, case):
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        in (
            "DATABASE_URL",
            "DB_PASSWORD_FILE",
            "OLLAMA_URL",
            "AI_MODE",
            "PATH",
            "HOME",
            "PYTHONPATH",
        )
    }
    env["WORKSPACE_ID"] = str(w)
    evidence = {}
    trace = []
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(os.path.dirname(__file__), "mcp_server.py")],
        env=env,
    )
    async with stdio_client(parameters) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            for tool, args in [
                ("search_cases", {"query": case["title"]}),
                ("get_study", {"study_id": case["study_id"]}),
                (
                    "search_knowledge",
                    {"query": case["title"] + " " + case["description"]},
                ),
                ("get_site", {"site_id": case["site_id"]}),
                (
                    "get_sync_jobs",
                    {"study_id": case["study_id"], "site_id": case["site_id"]},
                ),
                (
                    "get_document_processing",
                    {"study_id": case["study_id"], "site_id": case["site_id"]},
                ),
            ]:
                started = time.monotonic()
                result = await session.call_tool(tool, args)
                if result.isError:
                    raise ValueError("Evidence tool failed: " + tool)
                evidence.update(
                    json.loads(next(c.text for c in result.content if c.type == "text"))
                )
                trace.append(
                    {
                        "tool": tool,
                        "arguments": args,
                        "status": "success",
                        "duration_seconds": round(time.monotonic() - started, 3),
                    }
                )
    evidence["cases"] = [c for c in evidence.get("cases", []) if c["id"] != case["id"]]
    return evidence, trace


def collect_evidence(w, case):
    return asyncio.run(collect(w, case))
