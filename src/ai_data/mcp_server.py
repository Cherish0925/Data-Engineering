"""MCP is a transport over the same Python core, not a second implementation."""

from pathlib import Path

from .contracts import confined
from .pipeline import build, inspect_release, profile, verify_release
from .composition import compose, verify_mixture


def create_server(root: str | Path):
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as exc:
        raise ImportError('Install the MCP extra: python -m pip install -e ".[mcp]"') from exc
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("MCP workspace must be a directory")
    server = FastMCP("Data Engineering", instructions="Manage local data products within the configured workspace.")
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @server.tool(annotations=read)
    def data_capabilities() -> dict:
        """List implemented capabilities and data contract version."""
        return {"record_schema": "1.0", "connectors": ["jsonl", "gym-jsonl"],
                "operations": ["profile", "build", "inspect", "verify", "compose", "verify-mixture"],
                "scope": "local workspace; canonical release construction and streamed indexed mixture composition",
                "consumption": "Python MixtureReader with rank sharding and checkpoint state",
                "plugins": "disabled over MCP", "external_artifacts": "metadata references only"}

    @server.tool(annotations=read)
    def data_profile(path: str) -> dict:
        """Profile canonical JSONL records at a workspace-relative path."""
        return profile(confined(root, path))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
    def data_build(recipe: str, output: str) -> dict:
        """Build a new local release. Source paths are workspace-relative. Existing outputs are refused."""
        return build(confined(root, recipe), confined(root, output), root=root, allow_plugins=False)

    @server.tool(annotations=read)
    def data_inspect(path: str) -> dict:
        """Read a release manifest, without claiming its files have been verified."""
        return inspect_release(confined(root, path))

    @server.tool(annotations=read)
    def data_verify(path: str) -> dict:
        """Check local release hashes, partitions, declared use and counts; not external artifact bytes."""
        return verify_release(confined(root, path))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
    def data_compose(recipe: str, output: str) -> dict:
        """Compose pinned releases into budgeted indexed shards; paths are workspace-relative."""
        result = compose(confined(root, recipe), confined(root, output), root=root)
        return {key: result[key] for key in ("release_id", "name", "counts", "stop_reason", "sampling")}

    @server.tool(annotations=read)
    def data_verify_mixture(path: str) -> dict:
        """Check composed shard bytes, indexes and realized source/budget counts."""
        return verify_mixture(confined(root, path))

    return server
