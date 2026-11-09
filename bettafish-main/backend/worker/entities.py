"""实体对齐 v0（改造模块清单 §7 步骤③）。

规则：
- 统一社会信用代码（USCC）是 company 的 natural_key；
- 同名不同码 = 不同主体，**绝不合并**（防同名串档，对抗样本 adv_01 的核心场景）；
- 无 USCC 时按 display_name 精确匹配，唯一命中才复用；多命中抛 EntityAmbiguous；
- 别名（简称/曾用名）写 core.object_alias，不参与合并决策。

纯函数（normalize_uscc / plan_company_resolution）与 DB 包装分离，
前者可独立单测，后者懒加载 psycopg2（本地无 PG 也能 import 本模块的纯函数）。
"""

import re

from loguru import logger


class EntityAmbiguous(Exception):
    """无 USCC 且同名对象多于一个，无法自动对齐（需人工指定 USCC）。"""


# GB 32100-2015：18 位，本体码字符集不含 I/O/S/V/Z
USCC_RE = re.compile(r"^[0-9A-HJ-NPQRTUWXY]{18}$")


def normalize_uscc(uscc: str | None) -> str | None:
    """规整 USCC：去空白、转大写；不合法返回 None（调用方按无码处理并告警）。"""
    if not uscc:
        return None
    u = uscc.strip().upper()
    return u if USCC_RE.match(u) else None


def plan_company_resolution(
    display_name: str,
    uscc: str | None,
    same_uscc_row: dict | None,
    same_name_rows: list[dict],
) -> dict:
    """纯函数：根据查询结果决定 create / reuse / ambiguous。

    参数：
    - same_uscc_row: (object_type='company', natural_key=uscc) 的命中行（0 或 1 行）
    - same_name_rows: display_name 精确匹配的公司行（可能多行：同名不同码）

    返回：{"action": "reuse"|"create", "object_id"?, "name_conflict": bool}
    抛 EntityAmbiguous：无 USCC 且同名多于一个。
    """
    if uscc:
        if same_uscc_row is not None:
            return {"action": "reuse", "object_id": same_uscc_row["object_id"],
                    "name_conflict": False}
        # 有码但库中无此码：即使存在同名对象也新建（同名不同码不合并）
        return {"action": "create", "name_conflict": bool(same_name_rows)}
    # 无码：唯一同名才复用
    if len(same_name_rows) == 1:
        return {"action": "reuse", "object_id": same_name_rows[0]["object_id"],
                "name_conflict": False}
    if len(same_name_rows) > 1:
        raise EntityAmbiguous(
            f"存在 {len(same_name_rows)} 个名为「{display_name}」的对象且未提供 USCC，"
            "无法自动对齐；请提供统一社会信用代码后重试"
        )
    return {"action": "create", "name_conflict": False}


def resolve_company(
    display_name: str,
    uscc: str | None = None,
    display_meta: str | None = None,
    aliases: list[str] | None = None,
) -> dict:
    """实体对齐入口：返回 {"object_id", "created", "name_conflict"}。

    幂等：USCC 命中或唯一同名命中时复用既有对象；否则新建。
    新建时注册别名（简称等），便于后续搜索框一次查全。
    """
    from .store import get_conn  # 懒加载：模块导入不触发 psycopg2

    norm = normalize_uscc(uscc)
    if uscc and norm is None:
        logger.warning(f"USCC「{uscc}」不合法（非 18 位 GB 32100 字符集），按无码处理")

    with get_conn() as conn:
        import psycopg2.extras

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            same_uscc_row = None
            if norm:
                cur.execute(
                    "SELECT object_id FROM core.object "
                    "WHERE object_type = 'company' AND natural_key = %s",
                    (norm,),
                )
                same_uscc_row = cur.fetchone()
            cur.execute(
                "SELECT object_id, natural_key FROM core.object "
                "WHERE object_type = 'company' AND display_name = %s",
                (display_name,),
            )
            same_name_rows = cur.fetchall()

        plan = plan_company_resolution(display_name, norm, same_uscc_row, same_name_rows)

        if plan["action"] == "reuse":
            object_id = plan["object_id"]
            created = False
        else:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO core.object
                        (object_type, natural_key, display_name, display_meta)
                    VALUES ('company', %s, %s, %s)
                    RETURNING object_id
                    """,
                    (norm, display_name, display_meta),
                )
                object_id = cur.fetchone()[0]
            created = True
            if plan["name_conflict"]:
                logger.warning(
                    f"同名不同主体：新建对象 {object_id}「{display_name}」"
                    f"(USCC={norm})，与既有同名对象保持隔离，不合并"
                )

        if aliases:
            with conn.cursor() as cur:
                for alias in aliases:
                    if not alias or alias == display_name:
                        continue
                    alias_norm = alias.strip()
                    cur.execute(
                        """
                        INSERT INTO core.object_alias (object_id, alias, alias_norm, source)
                        VALUES (%s, %s, %s, 'entity_resolution')
                        ON CONFLICT (object_id, alias_norm) DO NOTHING
                        """,
                        (object_id, alias, alias_norm),
                    )

    return {
        "object_id": object_id,
        "created": created,
        "name_conflict": plan["name_conflict"],
    }


def assert_same_entity(object_row: dict, uscc: str | None, *, label: str = "证据") -> None:
    """入库前防串档校验：对象有 natural_key（USCC）时，传入 USCC 必须一致。

    供 case_file 等离线导入使用：同名不同码的数据拒绝落到同一对象。
    """
    norm = normalize_uscc(uscc)
    if norm and object_row.get("natural_key") and object_row["natural_key"] != norm:
        raise ValueError(
            f"{label}归属主体 USCC={norm} 与对象 {object_row['object_id']}"
            f"（{object_row.get('display_name')}，USCC={object_row['natural_key']}）不一致，"
            "疑似同名不同主体，拒绝入库以防串档"
        )
