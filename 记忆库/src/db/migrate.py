"""
数据库迁移入口 - 启动时自动执行所有迁移
"""

from src.system.logger import get_module_logger

logger = get_module_logger("migrate")


def migrate_db() -> dict:
    """
    执行所有数据库迁移，确保数据库结构完整
    """
    results = []

    # 导入所有迁移函数
    migrations = []

    try:
        from src.db.migrate_visibility import migrate_visibility

        migrations.append(("visibility", migrate_visibility))
    except ImportError:
        pass

    try:
        from src.db.migrate_value_fields import migrate_value_fields

        migrations.append(("value_fields", migrate_value_fields))
    except ImportError:
        pass

    try:
        from src.db.migrate_weight import migrate_weight

        migrations.append(("weight", migrate_weight))
    except ImportError:
        pass

    try:
        from src.db.migrate_edge_strength import migrate_edge_strength

        migrations.append(("edge_strength", migrate_edge_strength))
    except ImportError:
        pass

    try:
        from src.db.migrate_summary_item import migrate_summary_item

        migrations.append(("summary_item", migrate_summary_item))
    except ImportError:
        pass

    # 执行每个迁移
    for name, migrate_func in migrations:
        try:
            logger.info(f"[Migration] Running: {name}")
            result = migrate_func()
            if result.get("success"):
                logger.info(f"[Migration] {name}: OK")
            else:
                logger.warning(f"[Migration] {name}: {result.get('error')}")
            results.append({"name": name, "result": result})
        except Exception as e:
            logger.error(f"[Migration] {name}: FAILED - {e}")
            results.append(
                {"name": name, "result": {"success": False, "error": str(e)}}
            )

    success_count = sum(1 for r in results if r["result"].get("success"))
    logger.info(f"[Migration] Completed: {success_count}/{len(results)} migrations")

    return {
        "success": success_count == len(results),
        "results": results,
    }
