import base64
import mimetypes
import re
from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.generic.database import SQL
from diagrams.generic.network import Firewall, Router
from diagrams.generic.os import Ubuntu
from diagrams.onprem.client import User
from diagrams.onprem.network import Internet


# ============================================================
# Output path
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

OUTPUT_DIR = PROJECT_ROOT / "docs" / "architecture" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_NAME = "cnc_wp_infrastructure"
OUTPUT_PATH = OUTPUT_DIR / OUTPUT_NAME


# ============================================================
# SVG post-processing
# ============================================================

def embed_svg_images(svg_path: Path) -> None:
    """
    Convert local image references inside SVG into Base64 data URIs
    so the SVG renders correctly on GitHub and other environments.
    """
    if not svg_path.exists():
        print(f"[WARN] SVG not found: {svg_path}")
        return

    content = svg_path.read_text(encoding="utf-8")
    pattern = r'(?:xlink:href|href)="([^"]+)"'

    embedded_count = 0

    def replace_href(match):
        nonlocal embedded_count

        full_match = match.group(0)
        href = match.group(1)

        if href.startswith("data:"):
            return full_match

        image_path = Path(href)

        if not image_path.exists():
            return full_match

        mime_type, _ = mimetypes.guess_type(image_path.name)
        if mime_type is None:
            mime_type = "image/png"

        encoded = base64.b64encode(
            image_path.read_bytes()
        ).decode("ascii")

        embedded_count += 1
        attribute_name = full_match.split("=", 1)[0]

        return (
            f'{attribute_name}="data:{mime_type};base64,{encoded}"'
        )

    updated = re.sub(pattern, replace_href, content)
    svg_path.write_text(updated, encoding="utf-8")

    print(f"[OK] Embedded {embedded_count} SVG image(s): {svg_path}")


# ============================================================
# Graph style
# ============================================================

graph_attr = {
    "fontsize": "18",
    "pad": "0.5",
    "nodesep": "0.8",
    "ranksep": "1.1",
}


# ============================================================
# Infrastructure diagram
# ============================================================

with Diagram(
    "CNC WearPoint - NHN Cloud Infrastructure",
    filename=str(OUTPUT_PATH),
    outformat=["png", "svg"],
    show=False,
    direction="LR",
    graph_attr=graph_attr,
):

    # External access
    team = User("CNC WearPoint Team")
    internet = Internet("Internet")
    floating_ip = Router("Floating IP")

    with Cluster("NHN Cloud - cnc-wp-vpc\n10.60.0.0/20"):

        with Cluster("App Network\ncnc-wp-app-private\n10.60.0.64/27"):
            app_sg = Firewall(
                "cnc-wp-app-sg\n"
                "SSH 22\n"
                "14.36.141.67/32"
            )

            app_vm = Ubuntu(
                "cnc-wp-app-01\n"
                "Ubuntu 24.04 LTS\n"
                "m2.c2m4\n"
                "2 vCPU / 4GB\n"
                "SSD 150GB"
            )

            app_rt = Router(
                "cnc-wp-app-rt\n"
                "10.60.0.0/20 -> local\n"
                "0.0.0.0/0 -> IGW"
            )

            igw = Router("cnc-wp-igw")

        with Cluster("Database Network\ncnc-wp-db-private\n10.60.0.32/28"):
            db_sg = Firewall(
                "cnc-wp-db-sg\n"
                "DB Port\n"
                "Source: 10.60.0.64/27"
            )

            rds = SQL(
                "RDS for MySQL\n"
                "MySQL 8.4.6\n"
                "m2.c2m4\n"
                "General SSD 20GB"
            )

            private_rt = Router(
                "cnc-wp-private-rt\n"
                "Default Route Table\n"
                "10.60.0.0/20 -> local\n"
                "No IGW"
            )

    # ========================================================
    # Main flow
    # ========================================================

    team >> Edge(label="SSH 22") >> internet >> floating_ip >> app_sg >> app_vm
    app_vm >> Edge(label="MySQL DB Port") >> db_sg >> rds

    # ========================================================
    # Network configuration (supporting relationships)
    # ========================================================

    app_vm >> Edge(label="uses", style="dashed") >> app_rt
    app_rt >> Edge(label="default route", style="dashed") >> igw
    rds >> Edge(label="uses", style="dashed") >> private_rt


# ============================================================
# Post-process SVG
# ============================================================

SVG_FILE = OUTPUT_DIR / f"{OUTPUT_NAME}.svg"
embed_svg_images(SVG_FILE)