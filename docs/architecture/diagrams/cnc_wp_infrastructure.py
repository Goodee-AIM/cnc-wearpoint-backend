import base64
import mimetypes
import re
from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.generic.database import SQL
from diagrams.generic.network import Firewall, Router, Subnet
from diagrams.generic.os import Ubuntu
from diagrams.generic.storage import Storage
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
    Graphviz/Diagrams가 SVG 내부에 로컬 파일 경로로 기록한
    PNG 아이콘을 Base64 Data URI로 변환한다.

    이를 통해 GitHub나 다른 PC에서 SVG를 열어도
    로컬 .venv 경로에 의존하지 않고 아이콘을 표시할 수 있다.
    """

    if not svg_path.exists():
        print(f"[WARN] SVG not found: {svg_path}")
        return

    content = svg_path.read_text(encoding="utf-8")

    # Graphviz가 생성하는:
    # xlink:href="C:\\...\\icon.png"
    # href="C:\\...\\icon.png"
    # 두 형식을 모두 지원
    pattern = r'(?:xlink:href|href)="([^"]+)"'

    embedded_count = 0

    def replace_href(match):
        nonlocal embedded_count

        full_match = match.group(0)
        href = match.group(1)

        # 이미 Base64로 변환된 경우 그대로 유지
        if href.startswith("data:"):
            return full_match

        image_path = Path(href)

        # 실제 로컬 파일이 아닌 경우 그대로 유지
        if not image_path.exists():
            return full_match

        mime_type, _ = mimetypes.guess_type(image_path.name)

        if mime_type is None:
            mime_type = "image/png"

        encoded = base64.b64encode(
            image_path.read_bytes()
        ).decode("ascii")

        embedded_count += 1

        # 기존 SVG의 attribute 이름 유지
        attribute_name = full_match.split("=", 1)[0]

        return (
            f'{attribute_name}="'
            f'data:{mime_type};base64,{encoded}"'
        )

    updated = re.sub(pattern, replace_href, content)

    svg_path.write_text(
        updated,
        encoding="utf-8"
    )

    print(
        f"[OK] Embedded {embedded_count} SVG image(s): "
        f"{svg_path}"
    )


# ============================================================
# Graph style
# ============================================================

graph_attr = {
    "fontsize": "18",
    "pad": "0.5",
    "nodesep": "0.7",
    "ranksep": "1.0",
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

    # --------------------------------------------------------
    # External
    # --------------------------------------------------------

    team = User(
        "Development Team"
    )

    internet = Internet(
        "Internet"
    )

    floating_ip = Router(
        "Floating IP"
    )

    igw = Router(
        "cnc-wp-igw"
    )

    object_storage = Storage(
        "Object Storage\n"
        "Images / Model Artifacts\n"
        "(Planned)"
    )

    # --------------------------------------------------------
    # NHN Cloud VPC
    # --------------------------------------------------------

    with Cluster(
        "NHN Cloud - cnc-wp-vpc\n"
        "10.60.0.0/20"
    ):

        # ----------------------------------------------------
        # Application network
        # ----------------------------------------------------

        with Cluster(
            "App Network\n"
            "cnc-wp-app-private\n"
            "10.60.0.64/27"
        ):

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

        # ----------------------------------------------------
        # Database network
        # ----------------------------------------------------

        with Cluster(
            "Database Network\n"
            "cnc-wp-db-private\n"
            "10.60.0.32/28"
        ):

            db_sg = Firewall(
                "cnc-wp-db-sg\n"
                "DB Port\n"
                "Source: App /27"
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

        # ----------------------------------------------------
        # Future expansion
        # ----------------------------------------------------

        with Cluster(
            "Future Expansion"
        ):

            gpu_vm = Ubuntu(
                "GPU Integration Server\n"
                "T4 GPU\n"
                "Model Inference"
            )

            nks = Subnet(
                "NKS Worker Network\n"
                "10.60.4.0/22\n"
                "Kubeflow / Istio"
            )

            monitoring = Subnet(
                "Monitoring\n"
                "Prometheus / Grafana\n"
                "(Planned)"
            )

    # ========================================================
    # Network flows
    # ========================================================

    # Development team -> App VM SSH access
    team >> Edge(
        label="SSH 22"
    ) >> internet

    internet >> floating_ip >> app_sg >> app_vm

    # App subnet -> Internet Gateway
    app_vm >> app_rt >> igw >> internet

    # App -> RDS internal connection
    app_vm >> Edge(
        label="MySQL DB Port"
    ) >> db_sg >> rds

    # RDS uses private routing only
    rds - Edge(
        label="Private only",
        style="dashed"
    ) - private_rt

    # Future Object Storage
    app_vm >> Edge(
        label="Images / Artifacts",
        style="dashed"
    ) >> object_storage

    # Future GPU inference integration
    app_vm >> Edge(
        label="Future internal API",
        style="dashed"
    ) >> gpu_vm

    # Future NKS migration
    app_vm >> Edge(
        label="Future migration",
        style="dashed"
    ) >> nks

    # Future monitoring
    nks >> monitoring


# ============================================================
# Post-process SVG
# ============================================================

SVG_FILE = OUTPUT_DIR / f"{OUTPUT_NAME}.svg"

embed_svg_images(SVG_FILE)