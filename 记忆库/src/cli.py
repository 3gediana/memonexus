import argparse
import json
import sys
import ast
import os
import shutil

# 设置标准输出编码为UTF-8（解决Windows中文乱码问题）
sys.stdout.reconfigure(encoding="utf-8")

from src.system.config import load_config, save_config
from src.db.init import (
    init_database,
    init_sub_database,
    get_current_db_paths,
    get_table_schema,
)
from src.tools.key_tools import (
    init_keys_directory,
    list_key_dirs,
    get_current_keys_dir,
    create_key,
    get_key_overview,
)
from src.tools.memory_tools import (
    add_memory_to_key,
    replace_memory_in_key,
    delete_memory_from_key,
    list_memory_by_key,
)
from src.tools.edge_tools import create_edges, delete_edges, list_edges_by_fingerprint
from src.tools.sub_tools import insert_sub, query_sub_by_time, list_sub
from src.tools.routing_tools import assign_memory_to_keys
from src.tools.query_tools import (
    get_memory_by_fingerprint,
    get_key_context,
    get_cross_key_context,
)
from src.tools.recall_tools import dispatch_recall_to_keys, request_memory_recall
from src.system.fingerprint import generate_fingerprint, get_utc_now
from src.system.storage_flow import process_user_message
from src.system.freeze import FreezeManager
from src.system.freeze import FreezeManager
from src.system.context import assemble_context, get_assembly_status
from src.system.scheduler import KeyLock, AssociationQueue, ContextCommit
from src.agents import (
    RoutingAgent,
    KeyAgent,
    AssociationAgent,
    DialogueAgent,
    CompressionAgent,
)
from src.system.main import handle_user_message

ALLOWED_CONFIG_KEYS = [
    "freeze_timeout_seconds",
    "topk_default",
    "context_threshold",
    "idle_timeout",
    "max_memories_per_recall",
]


def main():
    parser = argparse.ArgumentParser(description="Memory Assistant CLI")
    subparsers = parser.add_subparsers(dest="command")

    # config子命令
    config_parser = subparsers.add_parser("config")
    config_parser.add_argument("action", choices=["show", "set", "reset"])
    config_parser.add_argument("key", nargs="?")
    config_parser.add_argument("value", nargs="?")

    # instance子命令
    instance_parser = subparsers.add_parser("instance")
    instance_parser.add_argument(
        "action", choices=["use", "current", "create", "list", "delete"]
    )
    instance_parser.add_argument("name", nargs="?")

    # db子命令
    db_parser = subparsers.add_parser("db")
    db_parser.add_argument("action", choices=["init", "schema", "query"])
    db_parser.add_argument("--table", help="Table name for schema command")
    db_parser.add_argument("--where", help="WHERE clause for query command")

    # key子命令
    key_parser = subparsers.add_parser("key")
    key_parser.add_argument(
        "action",
        choices=["init", "list-dirs", "create", "overview", "summary", "context"],
    )
    key_parser.add_argument("key", nargs="?")
    key_parser.add_argument("--no-summary", action="store_true")
    key_parser.add_argument("--key", dest="key_opt")

    # util子命令
    util_parser = subparsers.add_parser("util")
    util_parser.add_argument("action", choices=["fingerprint", "utc-now"])
    util_parser.add_argument("text", nargs="?")

    # edge子命令
    edge_parser = subparsers.add_parser("edge")
    edge_parser.add_argument(
        "action", choices=["create", "delete", "list", "calibrate"]
    )
    edge_parser.add_argument("--from-fp", dest="from_fp")
    edge_parser.add_argument("--to-fp", dest="to_fp")
    edge_parser.add_argument("--strength")
    edge_parser.add_argument("--reason")
    edge_parser.add_argument("--fingerprint", "--fp")

    # sub子命令
    sub_parser = subparsers.add_parser("sub")
    sub_parser.add_argument("action", choices=["insert", "query", "list", "memories"])
    sub_parser.add_argument("--message")
    sub_parser.add_argument("--turn")
    sub_parser.add_argument("--start")
    sub_parser.add_argument("--end")
    sub_parser.add_argument("--limit", type=int, default=50)
    sub_parser.add_argument("--offset", type=int, default=0)

    # routing子命令
    routing_parser = subparsers.add_parser("routing")
    routing_parser.add_argument("action", choices=["assign"])
    routing_parser.add_argument("--items")

    # memory子命令
    memory_parser = subparsers.add_parser("memory")
    memory_parser.add_argument(
        "action",
        choices=["add", "replace", "delete", "list", "get", "cross-context", "detail"],
    )
    memory_parser.add_argument("--key")
    memory_parser.add_argument("--memory")
    memory_parser.add_argument("--tag")
    memory_parser.add_argument("--summary-item")
    memory_parser.add_argument("--fingerprint", "--fp", action="append", default=[])
    memory_parser.add_argument("--old-fp", "--old-fingerprint")
    memory_parser.add_argument("--new-memory")
    memory_parser.add_argument("--new-tag")
    memory_parser.add_argument("--new-summary-item")
    memory_parser.add_argument("--format")

    # recall子命令
    recall_parser = subparsers.add_parser("recall")
    recall_parser.add_argument("action", choices=["dispatch", "request", "execute"])
    recall_parser.add_argument("--keys")
    recall_parser.add_argument("--request", dest="recall_request")
    recall_parser.add_argument("--target")
    recall_parser.add_argument("--topk", type=int, default=2)
    recall_parser.add_argument("--mode")
    recall_parser.add_argument("--time-start")
    recall_parser.add_argument("--time-end")

    # flow子命令
    flow_parser = subparsers.add_parser("flow")
    flow_parser.add_argument("action", choices=["store", "recall"])
    flow_parser.add_argument("--message")
    flow_parser.add_argument("--turn", type=int)
    flow_parser.add_argument("--mode", default="implicit")
    flow_parser.add_argument("--request")
    flow_parser.add_argument("--target")
    flow_parser.add_argument("--keys")
    flow_parser.add_argument("--topk", type=int, default=2)
    flow_parser.add_argument("--time-start")
    flow_parser.add_argument("--time-end")

    # freeze子命令
    freeze_parser = subparsers.add_parser("freeze")
    freeze_parser.add_argument(
        "action",
        choices=[
            "status",
            "test",
            "timeout-test",
            "activate",
            "deactivate",
            "clear-queue",
        ],
    )
    freeze_parser.add_argument("--timeout", type=int, default=15)

    # context子命令
    context_parser = subparsers.add_parser("context")
    context_parser.add_argument("action", choices=["assemble", "status"])
    context_parser.add_argument("--history")
    context_parser.add_argument("--system-prompt")
    context_parser.add_argument("--recall")
    context_parser.add_argument("--message")

    # scheduler子命令
    scheduler_parser = subparsers.add_parser("scheduler")
    scheduler_parser.add_argument(
        "action", choices=["status", "lock-test", "queue-test"]
    )
    scheduler_parser.add_argument("--key")

    # agent子命令
    agent_parser = subparsers.add_parser("agent")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")

    # agent routing
    agent_routing_parser = agent_subparsers.add_parser("routing")
    agent_routing_parser.add_argument("action", choices=["analyze"])
    agent_routing_parser.add_argument("--message")

    # agent key
    agent_key_parser = agent_subparsers.add_parser("key")
    agent_key_parser.add_argument("action", choices=["process", "recall"])
    agent_key_parser.add_argument("--key")
    agent_key_parser.add_argument("--candidate")
    agent_key_parser.add_argument("--tag")
    agent_key_parser.add_argument("--request")

    # agent association
    agent_association_parser = agent_subparsers.add_parser("association")
    agent_association_parser.add_argument("action", choices=["process"])
    agent_association_parser.add_argument("--fingerprint", "--fp")

    # agent dialogue
    agent_dialogue_parser = agent_subparsers.add_parser("dialogue")
    agent_dialogue_parser.add_argument("action", choices=["chat", "e2e"])
    agent_dialogue_parser.add_argument("--message")
    agent_dialogue_parser.add_argument("--messages")

    # agent compress
    agent_compress_parser = agent_subparsers.add_parser("compress")
    agent_compress_parser.add_argument("--history")

    # chat子命令 - 统一入口
    chat_parser = subparsers.add_parser("chat")
    chat_parser.add_argument("--message", required=True)
    chat_parser.add_argument("--turn", type=int, default=1)
    chat_parser.add_argument(
        "--debug", "-d", action="store_true", help="Enable debug output"
    )

    # session子命令
    session_parser = subparsers.add_parser("session")
    session_parser.add_argument("action", choices=["new", "store"])

    # cluster子命令
    cluster_parser = subparsers.add_parser("cluster")
    cluster_subparsers = cluster_parser.add_subparsers(dest="cluster_action")
    cluster_subparsers.add_parser("update")
    cluster_subparsers.add_parser("stats")

    cluster_info_parser = cluster_subparsers.add_parser("info")
    cluster_info_parser.add_argument("--cluster-id", required=True, help="Cluster ID")

    cluster_members_parser = cluster_subparsers.add_parser("members")
    cluster_members_parser.add_argument(
        "--cluster-id", required=True, help="Cluster ID"
    )

    cluster_assign_parser = cluster_subparsers.add_parser("assign")
    cluster_assign_parser.add_argument(
        "--fp", required=True, help="Fingerprint to assign"
    )
    cluster_assign_parser.add_argument(
        "--cluster-id", required=True, help="Target cluster ID"
    )

    # value子命令
    value_parser = subparsers.add_parser("value")
    value_subparsers = value_parser.add_subparsers(dest="value_action")

    value_calc_parser = value_subparsers.add_parser("calculate")
    value_calc_parser.add_argument("--key", help="Filter by key")
    value_calc_parser.add_argument(
        "--fingerprint", "--fp", help="Filter by fingerprint"
    )
    value_calc_parser.add_argument("--topk", type=int, default=10, help="Top K results")

    value_top_parser = value_subparsers.add_parser("top")
    value_top_parser.add_argument("--key", required=True, help="Key name")
    value_top_parser.add_argument("--topk", type=int, default=10, help="Top K results")

    value_subparsers.add_parser("update-all")
    value_subparsers.add_parser("prune")

    value_pagerank_parser = value_subparsers.add_parser("pagerank")
    value_pagerank_parser.add_argument("--key", help="Filter by key")

    # preference子命令
    pref_parser = subparsers.add_parser("preference")
    pref_subparsers = pref_parser.add_subparsers(dest="pref_action")
    pref_subparsers.add_parser("stats")
    pref_subparsers.add_parser("clear")
    pref_subparsers.add_parser("list")
    pref_subparsers.add_parser("factor")

    # monitor子命令
    monitor_parser = subparsers.add_parser("monitor")
    monitor_subparsers = monitor_parser.add_subparsers(dest="monitor_action")

    monitor_status_parser = monitor_subparsers.add_parser("status")
    monitor_status_parser.add_argument("--json", action="store_true")

    monitor_subparsers.add_parser("memory")
    monitor_subparsers.add_parser("edge")
    monitor_subparsers.add_parser("cluster")
    monitor_subparsers.add_parser("preference")

    # log子命令
    log_parser = subparsers.add_parser("log")
    log_subparsers = log_parser.add_subparsers(dest="log_action")

    log_show_parser = log_subparsers.add_parser("show")
    log_show_parser.add_argument("--lines", type=int, default=50)
    log_show_parser.add_argument(
        "--level", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )

    log_subparsers.add_parser("clear")

    # kb子命令
    kb_parser = subparsers.add_parser("kb")
    kb_subparsers = kb_parser.add_subparsers(dest="kb_action")

    kb_index_parser = kb_subparsers.add_parser("index")
    kb_index_parser.add_argument(
        "--paths", nargs="*", help="File/directory paths to index"
    )
    kb_index_parser.add_argument(
        "--force", action="store_true", help="Force reindex already indexed files"
    )

    kb_search_parser = kb_subparsers.add_parser("search")
    kb_search_parser.add_argument("--query", required=True, help="Search query")
    kb_search_parser.add_argument(
        "--topk", type=int, default=5, help="Number of results"
    )

    kb_subparsers.add_parser("list")
    kb_subparsers.add_parser("stats")

    kb_doc_parser = kb_subparsers.add_parser("document")
    kb_doc_parser.add_argument("--fp", required=True, help="Document fingerprint")

    kb_chunk_parser = kb_subparsers.add_parser("chunk")
    kb_chunk_parser.add_argument("--chunk-id", required=True, help="Chunk ID (fp-N)")

    kb_remove_parser = kb_subparsers.add_parser("remove")
    kb_remove_parser.add_argument(
        "--fp", required=True, help="Document fingerprint to remove"
    )

    # space子命令
    space_parser = subparsers.add_parser("space")
    space_subparsers = space_parser.add_subparsers(dest="space_action")

    space_add_parser = space_subparsers.add_parser("add")
    space_add_parser.add_argument("--content", required=True, help="Memory content")

    space_remove_parser = space_subparsers.add_parser("remove")
    space_remove_parser.add_argument("--id", type=int, required=True, help="Memory ID")

    space_update_parser = space_subparsers.add_parser("update")
    space_update_parser.add_argument("--id", type=int, required=True, help="Memory ID")
    space_update_parser.add_argument("--content", required=True, help="New content")

    space_subparsers.add_parser("list")

    # graph子命令
    graph_parser = subparsers.add_parser("graph")
    graph_subparsers = graph_parser.add_subparsers(dest="graph_action")
    graph_subparsers.add_parser("nodes")
    graph_subparsers.add_parser("edges")

    # visibility子命令
    vis_parser = subparsers.add_parser("visibility")
    vis_subparsers = vis_parser.add_subparsers(dest="vis_action")

    vis_update_parser = vis_subparsers.add_parser("update")
    vis_update_parser.add_argument("--fp", required=True, help="Fingerprint")
    vis_update_parser.add_argument(
        "--event",
        required=True,
        choices=["direct_hit", "associated_recall", "direct_miss"],
    )

    vis_check_parser = vis_subparsers.add_parser("check")
    vis_check_parser.add_argument("--fp", required=True, help="Fingerprint")

    vis_list_parser = vis_subparsers.add_parser("list")
    vis_list_parser.add_argument("--key", required=True, help="Key name")

    # weight子命令
    weight_parser = subparsers.add_parser("weight")
    weight_subparsers = weight_parser.add_subparsers(dest="weight_action")

    weight_info_parser = weight_subparsers.add_parser("info")
    weight_info_parser.add_argument("--fp", required=True, help="Fingerprint")

    # llm子命令
    llm_parser = subparsers.add_parser("llm")
    llm_parser.add_argument("action", choices=["chat"])
    llm_parser.add_argument("--message", required=True)
    llm_parser.add_argument(
        "--provider", choices=["minimax", "deepseek"], default="minimax"
    )

    args = parser.parse_args()

    if args.command == "config":
        handle_config(args)
    elif args.command == "instance":
        handle_instance(args)
    elif args.command == "db":
        handle_db(args)
    elif args.command == "key":
        handle_key(args)
    elif args.command == "util":
        handle_util(args)
    elif args.command == "memory":
        handle_memory(args)
    elif args.command == "edge":
        handle_edge(args)
    elif args.command == "sub":
        handle_sub(args)
    elif args.command == "routing":
        handle_routing(args)
    elif args.command == "recall":
        handle_recall(args)
    elif args.command == "flow":
        handle_flow(args)
    elif args.command == "freeze":
        handle_freeze(args)
    elif args.command == "context":
        handle_context(args)
    elif args.command == "scheduler":
        handle_scheduler(args)
    elif args.command == "agent":
        handle_agent(args)
    elif args.command == "chat":
        handle_chat(args)
    elif args.command == "session":
        handle_session(args)
    elif args.command == "cluster":
        handle_cluster(args)
    elif args.command == "value":
        handle_value(args)
    elif args.command == "preference":
        handle_preference(args)
    elif args.command == "monitor":
        handle_monitor(args)
    elif args.command == "log":
        handle_log(args)
    elif args.command == "kb":
        handle_kb(args)
    elif args.command == "space":
        handle_space(args)
    elif args.command == "graph":
        handle_graph(args)
    elif args.command == "visibility":
        handle_visibility(args)
    elif args.command == "weight":
        handle_weight(args)
    elif args.command == "llm":
        handle_llm(args)
    else:
        parser.print_help()


def handle_config(args):
    if args.action == "show":
        config = load_config()
        print(json.dumps(config, indent=2))
    elif args.action == "set":
        if args.key not in ALLOWED_CONFIG_KEYS:
            allowed = ", ".join(ALLOWED_CONFIG_KEYS)
            print(f"Error: Cannot set '{args.key}'. Allowed: {allowed}")
            sys.exit(1)
        config = load_config()
        config[args.key] = int(args.value)
        save_config(config)
        print(f"Set {args.key} = {args.value}")
    elif args.action == "reset":
        config = load_config()
        config["freeze_timeout_seconds"] = 15
        config["topk_default"] = 2
        config["context_threshold"] = 150000
        config["idle_timeout"] = 30
        config["max_memories_per_recall"] = 10
        save_config(config)
        print("Config reset to defaults")


def handle_instance(args):
    from src.system.config import create_instance, list_instances, switch_instance

    if args.action == "current":
        config = load_config()
        print(config["current_instance"])

    elif args.action == "use":
        if not args.name:
            print("Error: instance name required")
            sys.exit(1)
        result = switch_instance(args.name)
        if result["success"]:
            print(f"Switched to: {args.name}")
        else:
            print(f"Error: {result.get('error')}")
            sys.exit(1)

    elif args.action == "list":
        info = list_instances()
        print(f"Current: {info['current_instance']}")
        print("\nInstances:")
        for name, config in info["instances"].items():
            marker = " *" if name == info["current_instance"] else "  "
            print(f"{marker} {name}: {config.get('db_path', 'N/A')}")

    elif args.action == "create":
        if not args.name:
            print("Error: instance name required")
            sys.exit(1)

        result = create_instance(args.name)
        if not result["success"]:
            print(f"Error: {result.get('error')}")
            sys.exit(1)

        # 初始化数据库
        instance_config = result["instance"]
        from src.db.init import init_database, init_sub_database
        from src.tools.key_tools import init_keys_directory

        db_result = init_database(instance_config["db_path"])
        sub_result = init_sub_database(instance_config["sub_db_path"])
        keys_result = init_keys_directory(instance_config["keys_dir"])

        if db_result["success"] and sub_result["success"]:
            print(f"Instance created: {args.name}")
            print(f"  DB: {instance_config['db_path']}")
            print(f"  Sub DB: {instance_config['sub_db_path']}")
            print(f"  Keys: {instance_config['keys_dir']}")

            # 自动切换到新实例
            switch_instance(args.name)
            print(f"\nSwitched to: {args.name}")
        else:
            print(
                f"Error initializing database: {db_result.get('error') or sub_result.get('error')}"
            )
            sys.exit(1)

    elif args.action == "delete":
        if not args.name:
            print("Error: instance name required")
            sys.exit(1)

        import shutil
        from src.system.config import get_config, switch_instance

        config = get_config()
        current = config.get("current_instance")

        if args.name == current:
            print(f"Error: cannot delete current instance. Switch to another first.")
            sys.exit(1)

        instance = config.get("instances", {}).get(args.name)
        if not instance:
            print(f"Error: instance '{args.name}' not found")
            sys.exit(1)

        # 删除数据目录
        db_path = instance.get("db_path", "")
        if db_path:
            data_dir = os.path.dirname(db_path)
            if os.path.exists(data_dir):
                shutil.rmtree(data_dir)
                print(f"Deleted data directory: {data_dir}")

        # 从 config 中移除
        del config["instances"][args.name]
        save_config(config)
        print(f"Deleted instance: {args.name}")


def handle_db(args):
    config = load_config()
    instance_name = config["current_instance"]

    if args.action == "init":
        result1 = init_database()
        result2 = init_sub_database()
        if result1["success"] and result2["success"]:
            print("Database initialized successfully.")
            print(f"Instance: {instance_name}")
            print("Tables: memory, edges, sub")
        else:
            print(f"Error: {result1.get('error') or result2.get('error')}")
            sys.exit(1)
    elif args.action == "schema":
        if not args.table:
            print("Error: --table required for schema command")
            sys.exit(1)
        paths = get_current_db_paths()
        if args.table == "sub":
            result = get_table_schema(paths["sub_db_path"], args.table)
        else:
            result = get_table_schema(paths["db_path"], args.table)

        if result["success"]:
            print(f"Table: {result['table']}")
            print("Columns:")
            for col in result["columns"]:
                attrs = []
                if col["pk"]:
                    attrs.append("PRIMARY KEY")
                if col["notnull"]:
                    attrs.append("NOT NULL")
                attrs_str = ", ".join(attrs)
                if attrs_str:
                    print(f"  - {col['name']} ({col['type']}, {attrs_str})")
                else:
                    print(f"  - {col['name']} ({col['type']})")
            if result["indexes"]:
                idx_names = [idx["name"] for idx in result["indexes"]]
                print(f"Indexes: {', '.join(idx_names)}")
        else:
            print(f"Error: {result['error']}")
            sys.exit(1)
    elif args.action == "query":
        if not args.table:
            print("Error: --table required for query command")
            sys.exit(1)
        import sqlite3

        paths = get_current_db_paths()
        db_path = paths["sub_db_path"] if args.table == "sub" else paths["db_path"]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            sql = f"SELECT * FROM {args.table}"
            if args.where:
                sql += f" WHERE {args.where}"
            rows = conn.execute(sql).fetchall()
            for row in rows:
                print(dict(row))
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
        finally:
            conn.close()


def handle_key(args):
    if args.action == "init":
        result = init_keys_directory()
        if result["success"]:
            print("Keys directory initialized.")
        else:
            print(f"Error: {result['error']}")
            sys.exit(1)
    elif args.action == "list-dirs":
        result = list_key_dirs()
        if result["success"]:
            print(f"{result['keys_dir']}/")
            dirs = result["dirs"]
            for i, d in enumerate(dirs):
                if i == len(dirs) - 1:
                    print(f"└── {d}")
                else:
                    print(f"├── {d}")
        else:
            print(f"Error: {result['error']}")
            sys.exit(1)
    elif args.action == "create":
        result = create_key(args.key)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "overview":
        result = get_key_overview(include_summary=not args.no_summary)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "summary":
        import os
        from src.system.config import get_current_instance_config

        instance = get_current_instance_config()
        keys_dir = instance["keys_dir"]
        summary_file = os.path.join(keys_dir, args.key, "summary.json")
        if os.path.exists(summary_file):
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(data.get("summary", ""))
        else:
            print(f"Error: Key '{args.key}' not found")
            sys.exit(1)
    elif args.action == "context":
        key_name = args.key_opt or args.key
        if not key_name:
            print("Error: key required for context command")
            sys.exit(1)
        result = get_key_context(key_name)
        print(json.dumps(result, ensure_ascii=False))


def handle_util(args):
    if args.action == "fingerprint":
        if not args.text:
            print("Error: text argument required")
            sys.exit(1)
        print(generate_fingerprint(args.text))
    elif args.action == "utc-now":
        print(get_utc_now())


def handle_memory(args):
    if args.action == "add":
        result = add_memory_to_key(args.key, args.memory, args.tag, args.summary_item)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "replace":
        result = replace_memory_in_key(
            args.key, args.old_fp, args.new_memory, args.new_tag, args.new_summary_item
        )
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "delete":
        result = delete_memory_from_key(args.key, args.fingerprint)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "list":
        result = list_memory_by_key(args.key)
        if args.format == "simple":
            for m in result.get("memories", []):
                print(f"{m['fingerprint']} | {m['tag']} | {m['memory'][:50]}")
        else:
            print(json.dumps(result, ensure_ascii=False))
    elif args.action == "get":
        result = get_memory_by_fingerprint(args.fingerprint)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "cross-context":
        if not args.fingerprint:
            print("Error: --fp required for cross-context command")
            sys.exit(1)
        result = get_cross_key_context(args.fingerprint[0])
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "detail":
        if not args.fingerprint:
            print("Error: --fp required for detail command")
            sys.exit(1)
        fp = (
            args.fingerprint[0]
            if isinstance(args.fingerprint, list)
            else args.fingerprint
        )
        import sqlite3
        from src.db.init import get_current_db_paths
        from src.tools.edge_tools import list_edges_by_fingerprint

        paths = get_current_db_paths()
        conn = sqlite3.connect(paths["db_path"])
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM memory WHERE fingerprint = ?", (fp,)
        ).fetchone()
        conn.close()

        if not row:
            print(
                json.dumps(
                    {"success": False, "error": "Memory not found"}, ensure_ascii=False
                )
            )
            return

        memory_data = dict(row)
        edges = list_edges_by_fingerprint(fp)

        result = {
            "success": True,
            "memory": memory_data,
            "edges": edges,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


def handle_edge(args):
    if args.action == "create":
        result = create_edges(
            [
                {
                    "from_fingerprint": args.from_fp,
                    "to_fingerprint": args.to_fp,
                    "strength": float(args.strength),
                    "reason": args.reason,
                }
            ]
        )
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "delete":
        result = delete_edges(
            [{"from_fingerprint": args.from_fp, "to_fingerprint": args.to_fp}]
        )
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "list":
        result = list_edges_by_fingerprint(args.fingerprint)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.action == "calibrate":
        from src.tools.edge_calibrator import get_calibrator

        calibrator = get_calibrator()
        if args.from_fp and args.to_fp:
            result = calibrator.calibrate(args.from_fp, args.to_fp)
        else:
            result = calibrator.calibrate_all()
        print(json.dumps(result, ensure_ascii=False, indent=2))


def handle_sub(args):
    if args.action == "insert":
        result = insert_sub(args.message, int(args.turn))
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "query":
        result = query_sub_by_time(args.start, args.end)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "list":
        result = list_sub(limit=args.limit, offset=args.offset)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "memories":
        import sqlite3
        from src.db.init import get_current_db_paths

        paths = get_current_db_paths()
        conn = sqlite3.connect(paths["db_path"])
        conn.row_factory = sqlite3.Row
        if args.start:
            rows = conn.execute(
                "SELECT * FROM memory WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?",
                (args.start, args.limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memory ORDER BY created_at DESC LIMIT ?", (args.limit,)
            ).fetchall()
        conn.close()
        memories = [dict(row) for row in rows]
        print(
            json.dumps(
                {"success": True, "count": len(memories), "memories": memories},
                ensure_ascii=False,
                indent=2,
            )
        )


def handle_routing(args):
    if args.action == "assign":
        items = json.loads(args.items)
        result = assign_memory_to_keys(items)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "replace":
        result = replace_memory_in_key(
            args.key, args.old_fp, args.new_memory, args.new_tag, args.new_summary_item
        )
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "delete":
        result = delete_memory_from_key(args.key, args.fingerprint)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "list":
        result = list_memory_by_key(args.key)
        if args.format == "simple":
            for m in result.get("memories", []):
                print(f"{m['fingerprint']} | {m['tag']} | {m['memory'][:50]}")
        else:
            print(json.dumps(result, ensure_ascii=False))
    elif args.action == "get":
        from src.tools.memory_tools import get_memory_by_fingerprint

        result = get_memory_by_fingerprint(args.fingerprint)
        print(json.dumps(result, ensure_ascii=False))


def handle_recall(args):
    if args.action == "dispatch":
        if not args.keys:
            print("Error: --keys required for dispatch command")
            sys.exit(1)
        keys = [k.strip() for k in args.keys.split(",")]
        result = dispatch_recall_to_keys(
            keys, args.recall_request or "", args.target or "", args.topk
        )
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "request":
        if not args.mode:
            print("Error: --mode required for request command")
            sys.exit(1)
        keys = []
        if args.keys:
            keys = [k.strip() for k in args.keys.split(",")]
        time_scope = None
        if args.time_start and args.time_end:
            time_scope = {"start": args.time_start, "end": args.time_end}
        result = request_memory_recall(
            args.mode,
            args.recall_request or "",
            args.target or "",
            keys,
            time_scope,
            args.topk,
        )
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "execute":
        from src.system.recall_flow import RecallManager

        request_data = {
            "mode": args.mode or "implicit",
            "request": args.recall_request or "",
            "target": args.target or "",
            "keys": keys,
            "topk": args.topk,
        }
        if args.time_start and args.time_end:
            request_data["time_scope"] = {
                "start": args.time_start,
                "end": args.time_end,
            }
        manager = RecallManager()
        result = manager.execute_recall(request_data)
        print(json.dumps(result, ensure_ascii=False, indent=2))


def handle_flow(args):
    if args.action == "store":
        if not args.message or args.turn is None:
            print("Error: --message and --turn required for store command")
            sys.exit(1)
        result = process_user_message(args.message, args.turn)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "recall":
        if not args.request:
            print("Error: --request required for recall command")
            sys.exit(1)
        keys = []
        if args.keys:
            keys = [k.strip() for k in args.keys.split(",")]

        # 使用新的召回流程：从指定key召回
        if keys:
            from src.system.main import (
                _handle_recall_from_key,
                _expand_and_build_recall_blocks,
            )
            from src.agents.key_agent import KeyAgent
            from src.system.config import load_config
            from src.tools.memory_tools import list_memory_by_key
            from src.system.llm_client import chat_completion
            from src.system.retry import call_with_retry

            config = load_config()
            topk = config.get("topk_default", args.topk)

            all_recall_blocks = []
            for key in keys:
                key_memories = list_memory_by_key(key)
                if not key_memories["success"]:
                    continue

                memories = key_memories.get("memories", [])
                if not memories:
                    continue

                existing_for_agent = [
                    {"fingerprint": m["fingerprint"], "tag": m["tag"]} for m in memories
                ]
                agent_context = f"召回方向：{args.request}\n该key下的记忆（仅tag）：{json.dumps(existing_for_agent, ensure_ascii=False)}"

                def _key_agent_judge():
                    response = chat_completion(
                        messages=[
                            {
                                "role": "system",
                                "content": f"""你是"{key}"分类的记忆检索Agent。
根据用户的召回方向，从该分类下的记忆中判断哪些是相关的。

## 输入
- 召回方向：用户想找什么
- 记忆列表：只有tag标签和指纹

## 输出
调用get_relevant_memories工具，返回相关记忆的指纹列表。
如果没有相关记忆，返回空数组。
只根据tag判断相关性，不需要查看原文。""",
                            },
                            {"role": "user", "content": agent_context},
                        ],
                        tools=[
                            {
                                "type": "function",
                                "function": {
                                    "name": "get_relevant_memories",
                                    "description": "返回相关记忆的指纹列表",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "fingerprints": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                                "description": "相关记忆的指纹列表",
                                            },
                                        },
                                        "required": ["fingerprints"],
                                    },
                                },
                            }
                        ],
                        provider="deepseek",
                    )
                    if response.choices[0].message.tool_calls:
                        args_inner = json.loads(
                            response.choices[0].message.tool_calls[0].function.arguments
                        )
                        return args_inner.get("fingerprints", [])
                    return []

                relevant_fps = call_with_retry(_key_agent_judge)
                if relevant_fps:
                    blocks, _ = _expand_and_build_recall_blocks(relevant_fps, key, topk)
                    all_recall_blocks.extend(blocks)

            result = {"success": True, "recall_blocks": all_recall_blocks}
        else:
            result = {"success": False, "error": "Keys required for new recall flow"}
        print(json.dumps(result, ensure_ascii=False))


def handle_freeze(args):
    freeze_manager = FreezeManager()

    if args.action == "status":
        result = freeze_manager.get_status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.action == "activate":
        freeze_manager.freeze()
        print(
            json.dumps(
                {"success": True, "action": "frozen"}, ensure_ascii=False, indent=2
            )
        )
    elif args.action == "deactivate":
        result = freeze_manager.unfreeze()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.action == "clear-queue":
        freeze_manager.clear_queue()
        print(
            json.dumps(
                {"success": True, "action": "queue_cleared"},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.action == "test":
        # 测试冻结态状态机
        print("State: idle")
        freeze_manager.freeze()
        print("freeze() → State: frozen")
        freeze_manager.add_to_queue("消息1")
        print(f'add_to_queue("消息1") → Queue: {len(freeze_manager.get_queue())}')
        freeze_manager.add_to_queue("消息2")
        print(f'add_to_queue("消息2") → Queue: {len(freeze_manager.get_queue())}')
        print(f"get_queue() → {freeze_manager.get_queue()}")
        unfreeze_result = freeze_manager.unfreeze()
        print(f"unfreeze() → State: active, Queue cleared")
    elif args.action == "timeout-test":
        freeze_manager = FreezeManager(timeout_seconds=args.timeout)
        print("freeze() → State: frozen")
        freeze_manager.freeze()
        print(f"Waiting {args.timeout} seconds...")
        import time

        time.sleep(args.timeout)
        timed_out = freeze_manager.check_timeout()
        print(f"check_timeout() → {timed_out} (timed out)")


def handle_context(args):
    if args.action == "assemble":
        if (
            not args.history
            or not args.system_prompt
            or not args.recall
            or not args.message
        ):
            print(
                "Error: --history, --system-prompt, --recall, and --message required for assemble command"
            )
            sys.exit(1)
        recall_str = args.recall
        # 去除可能的首尾单引号
        if recall_str.startswith("'") and recall_str.endswith("'"):
            recall_str = recall_str[1:-1]
        try:
            recall_blocks = json.loads(recall_str)
        except json.JSONDecodeError:
            # 尝试用ast.literal_eval解析（支持单引号字符串）
            try:
                recall_blocks = ast.literal_eval(recall_str)
            except (ValueError, SyntaxError):
                print("Error: --recall must be valid JSON")
                sys.exit(1)
        from src.tools.memory_space_tools import get_memory_context_block

        memory_space = get_memory_context_block()
        result = assemble_context(
            args.history,
            args.system_prompt,
            recall_blocks,
            args.message,
            memory_space=memory_space,
        )
        print(result)
    elif args.action == "status":
        result = get_assembly_status()
        print(json.dumps(result, ensure_ascii=False))


def handle_scheduler(args):
    if args.action == "status":
        key_lock = KeyLock()
        association_queue = AssociationQueue()
        context_commit = ContextCommit()
        result = {
            "key_lock": key_lock.get_status(),
            "association_queue": {
                "size": association_queue.size(),
                "empty": association_queue.is_empty(),
            },
            "context_commit": {"pending_blocks": len(context_commit.get_pending())},
        }
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "lock-test":
        if not args.key:
            print("Error: --key required for lock-test command")
            sys.exit(1)
        key_lock = KeyLock()
        print(f"[{args.key}] lock acquired: {key_lock.acquire(args.key)}")
        key_lock.release(args.key)
        print(f"[{args.key}] lock released")
        print(f"[{args.key}] lock acquired again: {key_lock.acquire(args.key)}")
        key_lock.release(args.key)
        print(f"[{args.key}] lock released again")
    elif args.action == "queue-test":
        association_queue = AssociationQueue()
        association_queue.push("fp_001")
        print(f"push(fp_001) → queue: {association_queue.get_all()}")
        association_queue.push("fp_002")
        print(f"push(fp_002) → queue: {association_queue.get_all()}")
        popped = association_queue.pop()
        print(f"pop() → {popped}, queue: {association_queue.get_all()}")
        popped = association_queue.pop()
        print(f"pop() → {popped}, queue: {association_queue.get_all()}")
        popped = association_queue.pop()
        print(f"pop() → {popped} (empty)")


def handle_agent(args):
    from src.tools.key_tools import BUILT_IN_KEYS, get_key_overview
    from src.tools.memory_tools import add_memory_to_key, list_memory_by_key
    from src.tools.query_tools import get_key_context, get_cross_key_context
    from src.tools.edge_tools import create_edges

    if args.agent_command == "routing":
        if args.action == "analyze":
            if not args.message:
                print("Error: --message required for routing analyze")
                sys.exit(1)
            agent = RoutingAgent(BUILT_IN_KEYS)
            result = agent.analyze_message(args.message)
            print(json.dumps({"candidates": result}, ensure_ascii=False))

    elif args.agent_command == "key":
        if args.action == "process":
            if not args.key or not args.candidate:
                print("Error: --key and --candidate required for key process")
                sys.exit(1)
            agent = KeyAgent(args.key)
            # 获取已有记忆
            existing = list_memory_by_key(args.key)
            existing_memories = []
            if existing["success"]:
                for m in existing.get("memories", []):
                    existing_memories.append(
                        {
                            "fingerprint": m["fingerprint"],
                            "memory": m["memory"],
                            "tag": m["tag"],
                        }
                    )
            result = agent.process_candidate(
                args.candidate, args.tag or "", existing_memories
            )
            # 如果是add操作，实际写入数据库
            if result.get("action") == "add_memory_to_key":
                add_result = add_memory_to_key(
                    args.key,
                    args.candidate,
                    args.tag or "",
                    args.candidate,  # summary_item默认用memory
                )
                if add_result["success"]:
                    result["success"] = True
                    result["fingerprint"] = add_result["added"]["fingerprint"]
                else:
                    result["success"] = False
                    result["error"] = add_result.get("error")
            elif result.get("action") == "replace_memory_in_key":
                from src.tools.memory_tools import replace_memory_in_key

                replace_result = replace_memory_in_key(
                    args.key,
                    result["args"]["old_fingerprint"],
                    args.candidate,
                    args.tag or "",
                    args.candidate,
                )
                result["success"] = replace_result["success"]
                if replace_result["success"]:
                    result["fingerprint"] = replace_result["added"]["fingerprint"]
                else:
                    result["error"] = replace_result.get("error")
            elif result.get("action") == "reject_candidate":
                result["success"] = True
                result["reason"] = result["args"]["reason"]
            elif result.get("action") == "mark_duplicate":
                result["success"] = True
                result["existing_fingerprint"] = result["args"]["existing_fingerprint"]
            print(json.dumps(result, ensure_ascii=False))

        elif args.action == "recall":
            if not args.key or not args.request:
                print("Error: --key and --request required for key recall")
                sys.exit(1)
            context = get_key_context(args.key)
            if not context["success"]:
                print(json.dumps(context, ensure_ascii=False))
                return
            # 简单匹配tag
            matched = []
            for item in context.get("items", []):
                tag = item["tag"]
                if (
                    args.request.lower() in tag.lower()
                    or tag.lower() in args.request.lower()
                ):
                    matched.append(item["fingerprint"])
            # 如果没有匹配，返回所有
            if not matched:
                matched = [item["fingerprint"] for item in context.get("items", [])]
            print(json.dumps({"fingerprints": matched}, ensure_ascii=False))

    elif args.agent_command == "association":
        if args.action == "process":
            if not args.fingerprint:
                print("Error: --fp required for association process")
                sys.exit(1)
            # 获取主记忆和候选记忆
            cross_context = get_cross_key_context(args.fingerprint)
            if not cross_context["success"]:
                print(json.dumps(cross_context, ensure_ascii=False))
                return
            main_memory = cross_context["main_memory"]
            candidates = cross_context["candidates"]
            if not candidates:
                print(
                    json.dumps(
                        {
                            "main_fingerprint": args.fingerprint,
                            "candidates_checked": 0,
                            "edges_created": [],
                        },
                        ensure_ascii=False,
                    )
                )
                return
            agent = AssociationAgent()
            edges = agent.process(main_memory, candidates)
            # 实际创建边
            if edges:
                edge_list = []
                for edge in edges:
                    edge_list.append(
                        {
                            "from_fingerprint": args.fingerprint,
                            "to_fingerprint": edge["target_fingerprint"],
                            "strength": edge["strength"],
                            "reason": edge["reason"],
                        }
                    )
                create_result = create_edges(edge_list)
                if create_result["success"]:
                    edges_created = []
                    for e in create_result["created_edges"]:
                        edges_created.append(
                            {
                                "from": e["from"],
                                "to": e["to"],
                                "strength": 0.6,  # 从原始edges中获取
                            }
                        )
                    print(
                        json.dumps(
                            {
                                "main_fingerprint": args.fingerprint,
                                "candidates_checked": len(candidates),
                                "edges_created": edges_created,
                            },
                            ensure_ascii=False,
                        )
                    )
                else:
                    print(json.dumps(create_result, ensure_ascii=False))
            else:
                print(
                    json.dumps(
                        {
                            "main_fingerprint": args.fingerprint,
                            "candidates_checked": len(candidates),
                            "edges_created": [],
                        },
                        ensure_ascii=False,
                    )
                )

    elif args.agent_command == "dialogue":
        if args.action == "chat":
            if not args.message:
                print("Error: --message required for dialogue chat")
                sys.exit(1)
            agent = DialogueAgent(BUILT_IN_KEYS)
            result = agent.receive_message(args.message)
            print(json.dumps(result, ensure_ascii=False))

        elif args.action == "e2e":
            if not args.messages:
                print("Error: --messages required for dialogue e2e")
                sys.exit(1)
            messages = args.messages.split("|")
            agent = DialogueAgent(BUILT_IN_KEYS)
            conversation_history = []
            for msg in messages:
                result = agent.receive_message(msg)
                print(f"User: {msg}")
                if result["action"] == "reply":
                    print(f"Assistant: {result['content']}")
                    conversation_history.append({"role": "user", "content": msg})
                    conversation_history.append(
                        {"role": "assistant", "content": result["content"]}
                    )
                else:
                    print(
                        f"Assistant: [recall triggered] {json.dumps(result['params'], ensure_ascii=False)}"
                    )
                    conversation_history.append({"role": "user", "content": msg})
                print()

    elif args.agent_command == "compress":
        if not args.history:
            print("Error: --history required for compress")
            sys.exit(1)
        agent = CompressionAgent()
        result = agent.compress(args.history)
        print(result)


def handle_cluster(args):
    """处理cluster命令"""
    from src.tools.cluster_engine import get_cluster_engine

    engine = get_cluster_engine()

    if args.cluster_action == "update":
        result = engine.run_clustering()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.cluster_action == "stats":
        stats = engine.get_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))

    elif args.cluster_action == "info":
        info = engine.get_cluster_id(args.cluster_id)
        print(json.dumps(info, ensure_ascii=False, indent=2))

    elif args.cluster_action == "members":
        members = engine.get_cluster_memories(args.cluster_id)
        print(
            json.dumps(
                {"success": True, "cluster_id": args.cluster_id, "members": members},
                ensure_ascii=False,
                indent=2,
            )
        )

    elif args.cluster_action == "assign":
        from src.tools.cluster_service import assign_memory_to_cluster

        result = assign_memory_to_cluster(args.fp, args.cluster_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        print("Usage: cluster [update|stats|info|members|assign]")


def handle_value(args):
    """处理value命令"""
    from src.tools.value_assessor import get_value_assessor

    assessor = get_value_assessor()

    if args.value_action == "calculate":
        if args.fingerprint:
            result = assessor.calculate_value(args.fingerprint)
            print(json.dumps(result, ensure_ascii=False))
        elif args.key:
            result = assessor.get_top_valuable(args.key, args.topk)
            print(json.dumps(result, ensure_ascii=False))
        else:
            print("Error: --key or --fingerprint required")

    elif args.value_action == "top":
        result = assessor.get_top_valuable(args.key, args.topk)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.value_action == "update-all":
        result = assessor.update_all_values()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.value_action == "prune":
        result = assessor.prune_low_value_memories()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.value_action == "pagerank":
        result = assessor.compute_pagerank(args.key)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        print("Usage: value [calculate|top|update-all|prune|pagerank]")


def handle_chat(args):
    """处理chat命令 - 统一入口"""
    if not args.message:
        print("Error: --message required for chat command")
        sys.exit(1)

    if args.debug:
        from src.system.debug import set_debug_mode

        set_debug_mode(True)
        print("[DEBUG] Debug mode enabled\n")

    result = handle_user_message(args.message, args.turn)
    print(json.dumps(result, ensure_ascii=False))


def handle_session(args):
    """处理session命令"""
    from src.tools.session_tools import clear_session, get_session_messages

    if args.action == "new":
        result = clear_session()
        print(json.dumps(result, ensure_ascii=False))

    elif args.action == "store":
        messages = get_session_messages()
        if not messages:
            print(
                json.dumps(
                    {"success": True, "message": "No messages to store"},
                    ensure_ascii=False,
                )
            )
            return

        # 防重复：获取sub表中已有的消息
        existing_sub = list_sub()
        existing_messages = set()
        if existing_sub["success"]:
            for item in existing_sub.get("items", []):
                existing_messages.add(item["raw_message"])

        stored = []
        skipped = []

        for item in messages:
            message = item["message"]
            turn_index = item["turn_index"]

            # 防重复检查
            if message in existing_messages:
                skipped.append(message)
                continue

            # 存储消息
            result = process_user_message(message, turn_index)
            if result.get("success"):
                stored.append(message)
                existing_messages.add(message)
            else:
                print(f"Failed to store: {message}, error: {result.get('error')}")

        # 清空会话
        clear_session()

        print(
            json.dumps(
                {
                    "success": True,
                    "stored": len(stored),
                    "skipped": len(skipped),
                    "stored_messages": stored,
                    "skipped_messages": skipped,
                },
                ensure_ascii=False,
            )
        )


def handle_preference(args):
    """处理preference命令"""
    from src.tools.preference_tracker import get_preference_tracker

    tracker = get_preference_tracker()

    if args.pref_action == "stats":
        stats = tracker.get_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))

    elif args.pref_action == "clear":
        result = tracker.clear_history()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.pref_action == "list":
        prefs = tracker.get_all_preferences()
        print(json.dumps(prefs, ensure_ascii=False, indent=2))

    elif args.pref_action == "factor":
        factor = tracker.get_preference_factor()
        print(json.dumps({"preference_factor": factor}, ensure_ascii=False, indent=2))

    else:
        print("Usage: preference [stats|clear|list|factor]")


def handle_monitor(args):
    """Handle monitor command"""
    from src.tools.monitor import get_monitor

    monitor = get_monitor()

    if args.monitor_action == "status":
        if getattr(args, "json", False):
            report = monitor.get_full_report()
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            monitor.print_report()

    elif args.monitor_action == "memory":
        stats = monitor.get_memory_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))

    elif args.monitor_action == "edge":
        stats = monitor.get_edge_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))

    elif args.monitor_action == "cluster":
        stats = monitor.get_cluster_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))

    elif args.monitor_action == "preference":
        stats = monitor.get_preference_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))

    else:
        print("Usage: monitor [status|memory|edge|cluster|preference]")


def handle_log(args):
    """处理log命令"""
    import os
    import glob
    import logging
    import logging.handlers

    log_dir = "logs"

    if args.log_action == "show":
        if not os.path.exists(log_dir):
            print("No logs found")
            return

        log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]
        if not log_files:
            print("No log files found")
            return

        latest_log = max(log_files)
        log_path = os.path.join(log_dir, latest_log)

        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if args.level:
            lines = [l for l in lines if f"[{args.level}]" in l]

        for line in lines[-args.lines :]:
            print(line.rstrip())

    elif args.log_action == "clear":
        if os.path.exists(log_dir):
            # 关闭所有文件handler以释放文件锁
            for name in list(logging.Logger.manager.loggerDict.keys()):
                lgr = logging.getLogger(name)
                for hdlr in lgr.handlers[:]:
                    if isinstance(
                        hdlr,
                        (logging.FileHandler, logging.handlers.RotatingFileHandler),
                    ):
                        hdlr.close()
                        lgr.removeHandler(hdlr)

            log_files = glob.glob(os.path.join(log_dir, "*.log*"))
            cleared = 0
            for f in log_files:
                try:
                    os.remove(f)
                    cleared += 1
                except PermissionError:
                    pass
            print(f"Cleared {cleared} log files")
        else:
            print("No logs to clear")

    else:
        print("Usage: log [show|clear]")


def handle_kb(args):
    """Handle knowledge base commands"""
    from src.tools.kb_tools import execute_kb_tool

    if args.kb_action == "index":
        result = execute_kb_tool(
            "kb_index",
            {
                "paths": args.paths,
                "force_reindex": args.force,
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.kb_action == "search":
        result = execute_kb_tool(
            "kb_search",
            {
                "query": args.query,
                "topK": args.topk,
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.kb_action == "list":
        result = execute_kb_tool("kb_list_indexed", {})
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.kb_action == "stats":
        result = execute_kb_tool("kb_get_stats", {})
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.kb_action == "document":
        result = execute_kb_tool("kb_get_document", {"fingerprint": args.fp})
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.kb_action == "chunk":
        result = execute_kb_tool("kb_get_chunk", {"chunkId": args.chunk_id})
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.kb_action == "remove":
        result = execute_kb_tool("kb_remove_file", {"fingerprint": args.fp})
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        print("Usage: kb [index|search|list|stats|document|chunk|remove]")


def handle_space(args):
    """Handle memory space commands"""
    from src.tools.memory_space_tools import (
        add_memory,
        remove_memory,
        update_memory,
        list_memories,
    )

    if args.space_action == "add":
        result = add_memory(args.content)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.space_action == "remove":
        result = remove_memory(args.id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.space_action == "update":
        result = update_memory(args.id, args.content)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.space_action == "list":
        result = list_memories()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        print("Usage: space [add|remove|update|list]")


def handle_graph(args):
    """Handle graph export commands"""
    import sqlite3
    from src.db.init import get_current_db_paths

    paths = get_current_db_paths()
    conn = sqlite3.connect(paths["db_path"])
    conn.row_factory = sqlite3.Row

    if args.graph_action == "nodes":
        columns = [
            row["name"] for row in conn.execute("PRAGMA table_info(memory)").fetchall()
        ]
        select_cols = ["fingerprint", "key", "tag", "memory", "created_at"]
        for c in ["recall_count", "visibility", "value_score"]:
            if c in columns:
                select_cols.append(c)
        rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM memory").fetchall()
        nodes = []
        for row in rows:
            node = {
                "fingerprint": row["fingerprint"],
                "key": row["key"],
                "tag": row["tag"],
                "memory_preview": row["memory"][:80] if row["memory"] else "",
                "created_at": row["created_at"],
            }
            for c in ["recall_count", "visibility", "value_score"]:
                if c in columns:
                    node[c] = row[c]
            nodes.append(node)
        conn.close()
        print(
            json.dumps(
                {"success": True, "count": len(nodes), "nodes": nodes},
                ensure_ascii=False,
                indent=2,
            )
        )

    elif args.graph_action == "edges":
        rows = conn.execute(
            "SELECT from_fingerprint, to_fingerprint, strength, reason, created_at FROM edges"
        ).fetchall()
        edges = []
        for row in rows:
            edge = {
                "from": row["from_fingerprint"],
                "to": row["to_fingerprint"],
                "strength": row["strength"],
                "reason": row["reason"],
                "created_at": row["created_at"],
            }
            edges.append(edge)
        conn.close()
        print(
            json.dumps(
                {"success": True, "count": len(edges), "edges": edges},
                ensure_ascii=False,
                indent=2,
            )
        )

    else:
        print("Usage: graph [nodes|edges]")


def handle_visibility(args):
    """Handle visibility commands"""
    from src.tools.visibility_tools import (
        update_visibility,
        is_visible,
        get_visible_memories,
    )

    if args.vis_action == "update":
        result = update_visibility(args.fp, args.event)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.vis_action == "check":
        visible = is_visible(args.fp)
        print(
            json.dumps(
                {"fingerprint": args.fp, "visible": visible},
                ensure_ascii=False,
                indent=2,
            )
        )

    elif args.vis_action == "list":
        memories = get_visible_memories(args.key)
        print(
            json.dumps(
                {
                    "success": True,
                    "key": args.key,
                    "count": len(memories),
                    "memories": memories,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    else:
        print("Usage: visibility [update|check|list]")


def handle_weight(args):
    """Handle weight commands"""
    from src.tools.weight_tools import get_memory_weight_info

    if args.weight_action == "info":
        result = get_memory_weight_info(args.fp)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        print("Usage: weight info --fp <fingerprint>")


def handle_llm(args):
    """Handle direct LLM chat commands"""
    from src.system.llm_client import chat_completion

    result = chat_completion(
        messages=[{"role": "user", "content": args.message}],
        provider=args.provider,
    )
    content = result.choices[0].message.content
    print(content)


if __name__ == "__main__":
    main()
