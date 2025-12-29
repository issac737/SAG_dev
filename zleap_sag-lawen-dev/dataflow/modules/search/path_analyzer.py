"""
路径分析器 - 计算从 query 到 final event 的所有完整路径

基于线索(clues)数据，使用 DFS 反推算法计算所有完整推理路径，
支持最短路径、最长路径分析，为前端知识图谱精简模式提供数据支持。

注意：此模块不会修改传入的 clues 数据，所有操作都基于深拷贝。
"""

import copy
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from dataflow.utils import get_logger

logger = get_logger("search.path_analyzer")


@dataclass
class PathNode:
    """
    路径节点

    Attributes:
        id: 节点唯一ID
        type: 节点类型 (query, entity, event, section)
        content: 节点显示内容
        stage: 所属阶段 (recall, expand, rerank)
        hop: 跳数（Expand 阶段）
        metadata: 附加元数据
    """
    id: str
    type: str
    content: str
    stage: str
    hop: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "stage": self.stage,
            "hop": self.hop,
            "metadata": self.metadata,
        }


@dataclass
class PathLine:
    """
    完整路径线（从 query 到 final event）

    一条 line 代表一条完整的推理路径

    Attributes:
        id: 路径唯一ID
        nodes: 路径上的所有节点（有序，从 query 到 event）
        clue_ids: 对应的线索ID列表
        total_confidence: 路径总置信度
        length: 路径长度（边数）
        stages: 经过的阶段列表
        event_id: 最终事项的数据库ID
    """
    id: str
    nodes: List[PathNode]
    clue_ids: List[str]
    total_confidence: float
    length: int
    stages: List[str]
    event_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nodes": [node.to_dict() for node in self.nodes],
            "clue_ids": self.clue_ids,
            "total_confidence": self.total_confidence,
            "length": self.length,
            "stages": self.stages,
            "event_id": self.event_id,
        }


@dataclass
class PathAnalysisResult:
    """
    路径分析结果

    Attributes:
        min_lines: 每个事项的最短路径（富含完整数据格式）
        max_lines: 每个事项的最长路径（富含完整数据格式）
        entitys: 按跳数分组的实体统计
        rerank_lines: 每个事项的所有路径（列表格式）
    """
    min_lines: Dict[str, List[Dict[str, Any]]]  # {"event-id": [{"query": ...}, {"entity": ...}, {"event": ...}]}
    max_lines: Dict[str, List[Dict[str, Any]]]  # {"event-id": [{"query": ...}, {"entity": ...}, {"event": ...}]}
    entitys: Dict[str, List[Dict[str, Any]]]  # {"0": [], "1": [], "2": []}
    rerank_lines: Dict[str, List[List[Dict[str, Any]]]]  # {"event-id": [[path1], [path2], ...]}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_lines": self.min_lines,
            "max_lines": self.max_lines,
            "entitys": self.entitys,
            "rerank_lines": self.rerank_lines,
        }


class PathAnalyzer:
    """
    路径分析器

    从线索列表中计算所有完整路径（query → final event）
    使用 DFS 反推算法，从 Rerank 阶段的 final 线索开始，
    反向追溯到 Query 节点。
    """

    def __init__(self, clues: List[Dict[str, Any]]):
        """
        初始化路径分析器

        Args:
            clues: 线索列表（来自 config.all_clues）

        注意：会对 clues 进行深拷贝，不会修改原始数据
        """
        # 深拷贝，确保不修改原始数据
        self.clues = copy.deepcopy(clues)
        self.logger = get_logger("search.path_analyzer")

        # 图结构
        self.forward_graph: Dict[str, List[Tuple[str, Dict]]] = defaultdict(list)
        self.reverse_graph: Dict[str, List[Tuple[str, Dict]]] = defaultdict(list)
        self.nodes: Dict[str, Dict] = {}
        self.final_clues: List[Dict] = []
        self.query_nodes: Set[str] = set()

        # 构建图
        self._build_graph()

    def _build_graph(self):
        """构建邻接表和反向邻接表"""
        # 🔍 诊断：检测循环引用
        potential_cycles = []

        for clue in self.clues:
            from_node = clue.get("from", {})
            to_node = clue.get("to", {})
            from_id = from_node.get("id")
            to_id = to_node.get("id")

            if not from_id or not to_id:
                continue

            # 存储节点信息
            self.nodes[from_id] = from_node
            self.nodes[to_id] = to_node

            # 构建正向和反向图
            self.forward_graph[from_id].append((to_id, clue))
            self.reverse_graph[to_id].append((from_id, clue))

            # 识别 query 节点
            if from_node.get("type") == "query":
                self.query_nodes.add(from_id)

            # 识别 final 线索（Rerank 阶段的最终结果）
            if clue.get("display_level") == "final" and clue.get("stage") == "rerank":
                self.final_clues.append(clue)

            # 🔍 诊断：检测潜在的双向边（可能导致循环）
            # 检查是否存在反向边：to_id → from_id
            if to_id in self.forward_graph:
                for existing_to, existing_clue in self.forward_graph[to_id]:
                    if existing_to == from_id:
                        potential_cycles.append({
                            "node1_id": from_id[:20],
                            "node1_type": from_node.get("type"),
                            "node1_content": from_node.get("content", "")[:20],
                            "node2_id": to_id[:20],
                            "node2_type": to_node.get("type"),
                            "node2_content": to_node.get("content", "")[:20],
                            "clue1_stage": clue.get("stage"),
                            "clue2_stage": existing_clue.get("stage"),
                        })

        self.logger.debug(
            f"图构建完成: {len(self.nodes)} 节点, "
            f"{len(self.clues)} 边, "
            f"{len(self.final_clues)} 条 final 线索, "
            f"{len(self.query_nodes)} 个 query 节点"
        )

        # 🔍 输出循环检测结果
        if potential_cycles:
            self.logger.warning(
                f"🔁 检测到 {len(potential_cycles)} 对潜在的双向边（可能导致路径断裂）:"
            )
            for cycle in potential_cycles[:5]:  # 只显示前5个
                self.logger.warning(
                    f"  • {cycle['node1_type']} '{cycle['node1_content']}' ({cycle['node1_id']}...) "
                    f"↔ {cycle['node2_type']} '{cycle['node2_content']}' ({cycle['node2_id']}...) "
                    f"[stage: {cycle['clue1_stage']} ↔ {cycle['clue2_stage']}]"
                )
            if len(potential_cycles) > 5:
                self.logger.warning(f"  ... 还有 {len(potential_cycles) - 5} 对双向边未显示")
        else:
            self.logger.info("✅ 未检测到双向边，图结构正常")

    def analyze(self, target_event_ids: Optional[List[str]] = None) -> PathAnalysisResult:
        """
        分析所有路径

        Args:
            target_event_ids: 目标事项ID列表（仅分析这些事项的路径）
                             如果为 None，则分析所有 final 线索

        Returns:
            PathAnalysisResult: 包含所有路径、最短/最长路径和统计信息
        """
        all_lines: List[PathLine] = []

        # 🔧 根据 target_event_ids 过滤 final_clues
        if target_event_ids is not None:
            # 将目标事项ID转为集合，方便快速查找
            target_id_set = set(target_event_ids)
            filtered_final_clues = []

            for clue in self.final_clues:
                to_node = clue.get("to", {})
                event_id = to_node.get("event_id") or to_node.get("id")
                if event_id in target_id_set:
                    filtered_final_clues.append(clue)

            self.logger.info(
                f"开始路径分析: 从 {len(self.final_clues)} 条 final 线索中筛选出 "
                f"{len(filtered_final_clues)} 条目标事项的线索"
            )
            final_clues_to_analyze = filtered_final_clues
        else:
            self.logger.info(f"开始路径分析: {len(self.final_clues)} 条 final 线索")
            final_clues_to_analyze = self.final_clues

        # 从每个 final 线索反推完整路径
        for final_clue in final_clues_to_analyze:
            to_node = final_clue.get("to", {})
            event_id = to_node.get("event_id") or to_node.get("id")

            # DFS 反推所有路径
            paths = self._find_all_paths_to_query(final_clue)

            # 改为 info 级别,方便排查路径丢失问题
            if len(paths) == 0:
                # 🔧 调试：输出 final_clue 的详细信息
                from_node = final_clue.get("from", {})
                self.logger.warning(
                    f"⚠️ Final event {event_id}: 找到 0 条路径"
                )
                self.logger.warning(
                    f"   Final clue: {from_node.get('type')}(id={from_node.get('id')[:30]}...) "
                    f"→ {to_node.get('type')}(id={to_node.get('id')[:30]}...)"
                )
                # 检查 from_node 是否有父节点
                from_id = from_node.get("id")
                parents = self.reverse_graph.get(from_id, [])
                self.logger.warning(
                    f"   From节点 '{from_id[:30]}...' 的父节点数量: {len(parents)}"
                )
                if len(parents) == 0:
                    self.logger.warning(
                        f"   ❌ From节点没有父节点，路径中断！"
                    )
                    # 输出 from 节点的详细信息
                    self.logger.warning(
                        f"   From节点详情: type={from_node.get('type')}, "
                        f"content={from_node.get('content', '')[:30]}, "
                        f"stage={final_clue.get('stage')}"
                    )
                else:
                    # 输出父节点的详细信息
                    parent_details = []
                    for parent_id, parent_clue in parents[:3]:
                        parent_node_data = self.nodes.get(parent_id, {})
                        parent_type = parent_node_data.get("type", "unknown")
                        parent_stage = parent_clue.get('stage')
                        parent_content = parent_node_data.get('content', '')[:20]
                        parent_details.append({
                            'id': parent_id[:20],
                            'type': parent_type,
                            'stage': parent_stage,
                            'content': parent_content
                        })

                    self.logger.warning(
                        f"   父节点列表 (前3个): {parent_details}"
                    )

                    # 🔧 检查：如果父节点是 event，继续检查这个 event 有没有父节点
                    for parent_id, parent_clue in parents[:1]:
                        parent_node_data = self.nodes.get(parent_id, {})
                        parent_type = parent_node_data.get("type", "unknown")
                        if parent_type == "event":
                            # 检查这个 event 节点的父节点
                            event_parents = self.reverse_graph.get(parent_id, [])
                            self.logger.warning(
                                f"   → 父节点是 event '{parent_id[:20]}...', "
                                f"它的父节点数量: {len(event_parents)}"
                            )
                            if len(event_parents) == 0:
                                self.logger.error(
                                    f"   ❌ Event 父节点没有更上层的父节点，路径在此中断！"
                                )
                            else:
                                # 输出 event 的父节点
                                event_parent_details = []
                                for ep_id, ep_clue in event_parents[:3]:
                                    ep_data = self.nodes.get(ep_id, {})
                                    event_parent_details.append({
                                        'id': ep_id[:20],
                                        'type': ep_data.get('type'),
                                        'stage': ep_clue.get('stage')
                                    })
                                self.logger.warning(
                                    f"   → Event 的父节点: {event_parent_details}"
                                )

                                # 🔧 继续检查 event 的父节点（entity）是否有父节点
                                for ep_id, ep_clue in event_parents[:1]:
                                    ep_data = self.nodes.get(ep_id, {})
                                    ep_type = ep_data.get('type')
                                    entity_parents = self.reverse_graph.get(ep_id, [])
                                    self.logger.warning(
                                        f"   → → Entity '{ep_id[:20]}...' (type={ep_type}) 的父节点数量: {len(entity_parents)}"
                                    )
                                    if len(entity_parents) == 0:
                                        self.logger.error(
                                            f"   ❌❌ Entity 节点没有父节点，路径在此彻底中断！"
                                        )
                                    else:
                                        # 显示这个实体的父节点
                                        entity_parent_details = []
                                        for eep_id, eep_clue in entity_parents[:3]:
                                            eep_data = self.nodes.get(eep_id, {})
                                            entity_parent_details.append({
                                                'id': eep_id[:20],
                                                'type': eep_data.get('type'),
                                                'stage': eep_clue.get('stage')
                                            })
                                        self.logger.warning(
                                            f"   → → Entity 的父节点: {entity_parent_details}"
                                        )
            else:
                self.logger.debug(
                    f"Final event {event_id}: 找到 {len(paths)} 条路径"
                )

            for path_nodes, path_clues in paths:
                # 计算路径置信度（边置信度的乘积）
                confidences = [c.get("confidence", 1.0) for c in path_clues]
                total_confidence = 1.0
                for conf in confidences:
                    total_confidence *= conf

                # 提取经过的阶段（去重保序）
                stages = []
                for clue in path_clues:
                    stage = clue.get("stage")
                    if stage and (not stages or stages[-1] != stage):
                        stages.append(stage)

                # 🆕 调试：检查路径中的节点类型和跳数
                node_types = [n.type for n in path_nodes]
                entity_hops = [n.hop for n in path_nodes if n.type == "entity"]

                if len(paths) <= 3 and len(all_lines) <= 10:  # 只在前面几条路径输出详细日志
                    self.logger.debug(
                        f"路径构建: 节点类型={node_types}, "
                        f"实体跳数={entity_hops}, 阶段={stages}"
                    )
                    # 🐛 输出每个实体节点的详细信息
                    for idx, node in enumerate(path_nodes):
                        if node.type == "entity":
                            self.logger.debug(
                                f"  实体[{idx}]: id={node.id[:30]}, "
                                f"content={node.content[:20]}, hop={node.hop}, stage={node.stage}"
                            )

                line = PathLine(
                    id=str(uuid.uuid4()),
                    nodes=path_nodes,
                    clue_ids=[c.get("id", "") for c in path_clues],
                    total_confidence=round(total_confidence, 4),
                    length=len(path_clues),
                    stages=stages,
                    event_id=event_id,  # 改为 event_id
                )
                all_lines.append(line)

        # 去重
        all_lines = self._deduplicate_lines(all_lines)

        # 🆕 统计 entitys（按跳数分组）- 传入所有路径用于统计
        entitys = self._build_entitys_by_hop(all_lines)

        # 🆕 构建 rerank_lines（所有路径的富含数据）- 使用 all_lines
        rerank_lines = self._build_all_event_lines(all_lines)

        # 🆕 从 rerank_lines 中直接提取 min_lines 和 max_lines
        min_lines = self._extract_min_lines_from_rerank(rerank_lines)
        max_lines = self._extract_max_lines_from_rerank(rerank_lines)

        # 检查是否有事项路径丢失
        # 🔧 修复：应该统计有多少个唯一事项有 final 线索
        final_event_ids = set()
        for clue in final_clues_to_analyze:
            to_node = clue.get("to", {})
            event_id = to_node.get("event_id") or to_node.get("id")
            final_event_ids.add(event_id)

        final_event_count = len(final_event_ids)
        found_event_count = len(min_lines)

        if final_event_count != found_event_count:
            missing_event_ids = final_event_ids - set(min_lines.keys())
            self.logger.warning(
                f"⚠️ 路径构建差异: 目标 {final_event_count} 个事项, "
                f"但只找到 {found_event_count} 个事项的完整路径 "
                f"(丢失 {final_event_count - found_event_count} 个)"
            )
            if missing_event_ids:
                self.logger.warning(
                    f"   缺失路径的事项ID: {list(missing_event_ids)[:5]}"
                )
        else:
            self.logger.info(
                f"✅ 所有 {final_event_count} 个目标事项都找到了完整路径"
            )

        self.logger.info(
            f"路径分析完成: 总路径数={len(all_lines)}, "
            f"事项数={len(min_lines)}"
        )

        return PathAnalysisResult(
            min_lines=min_lines,  # 富含完整数据格式（最短路径）：{"event-id": [{"query": ...}, ...]}
            max_lines=max_lines,  # 富含完整数据格式（最长路径）：{"event-id": [{"query": ...}, ...]}
            entitys=entitys,
            rerank_lines=rerank_lines,  # 所有路径：{"event-id": [[path1], [path2], ...]}
        )

    def _find_all_paths_to_query(
        self,
        final_clue: Dict,
        max_depth: int = 10,
    ) -> List[Tuple[List[PathNode], List[Dict]]]:
        """
        从 final 线索反推到 query 的所有路径

        使用 DFS 回溯算法

        Args:
            final_clue: 最终线索
            max_depth: 最大搜索深度（防止死循环）

        Returns:
            List of (节点列表, 线索列表) 元组
        """
        all_paths = []

        def dfs(
            current_node_id: str,
            path_nodes: List[PathNode],
            path_clues: List[Dict],
            visited: Set[str],
            depth: int,
        ):
            # 🔍 调试：记录 DFS 进入
            current_node_data = self.nodes.get(current_node_id, {})
            current_node_type = current_node_data.get("type", "unknown")
            current_node_content = current_node_data.get("content", "")[:20]

            # 🔧 移除深度限制，依赖 visited 集合防止循环
            # if depth > max_depth:
            #     self.logger.warning(
            #         f"⚠️ DFS达到最大深度{max_depth}: node={current_node_id[:20]}... "
            #         f"(type={current_node_type}, content='{current_node_content}')"
            #     )
            #     return

            # 到达 origin query 节点，找到一条完整路径
            # 🔧 修复：只有 category="origin" 的 query 才是真正的起点
            # 如果是 rewrite query，需要继续往上追溯到 origin query
            if current_node_id in self.query_nodes:
                node_data = self.nodes.get(current_node_id, {})
                category = node_data.get("category", "origin")

                # 只有 origin query 才停止
                if category == "origin":
                    # 路径是反向的，需要翻转
                    all_paths.append((
                        list(reversed(path_nodes)),
                        list(reversed(path_clues))
                    ))
                    self.logger.debug(
                        f"✅ DFS找到完整路径: 长度={len(path_nodes)}, depth={depth}"
                    )
                    return
                # rewrite query 继续往上追溯

            # 获取所有父节点
            parents = self.reverse_graph.get(current_node_id, [])

            # 🔍 调试：记录父节点数量
            if len(parents) == 0:
                self.logger.warning(
                    f"⚠️ DFS遇到断点（无父节点）: node={current_node_id[:20]}... "
                    f"(type={current_node_type}, content='{current_node_content}'), depth={depth}"
                )

            # 🔧 修复：如果当前节点是 event（且不是最终的 final event），
            # 需要继续往上追溯，因为路径可能是 query → entity → event → entity → final_event
            current_node_data = self.nodes.get(current_node_id, {})
            current_node_type = current_node_data.get("type", "")

            for parent_id, clue in parents:
                if parent_id in visited:
                    # 🔧 调试：记录遇到环的情况
                    parent_data = self.nodes.get(parent_id, {})
                    self.logger.warning(
                        f"⚠️ DFS遇到环: current_node={current_node_id[:20]}..., "
                        f"parent_id={parent_id[:30]}..., "
                        f"type={parent_data.get('type')}, "
                        f"content={parent_data.get('content', '')[:20]}, "
                        f"当前深度={depth}, "
                        f"visited={[vid[:8] for vid in list(visited)[:5]]}"
                    )
                    continue  # 避免环

                # 🔧 修复：从 clue 的 from 节点获取准确的 hop 值
                # parent 是反向追溯，所以 parent_id 对应 clue 的 from 节点
                clue_from = clue.get("from", {})
                parent_data = self.nodes.get(parent_id, {})

                # 优先使用 clue 中的 hop（更准确），fallback 到 parent_data
                parent_hop = clue_from.get("hop", parent_data.get("hop", 0))

                # 🐛 调试日志：检查 hop 来源
                if parent_data.get("type") == "entity" and clue_from.get("hop") != parent_data.get("hop"):
                    self.logger.debug(
                        f"⚠️ Hop 不一致: entity={parent_id[:20]}..., "
                        f"clue.from.hop={clue_from.get('hop')}, "
                        f"nodes.hop={parent_data.get('hop')}, "
                        f"使用 clue.from.hop={parent_hop}"
                    )

                parent_node = PathNode(
                    id=parent_id,
                    type=parent_data.get("type", "unknown"),
                    content=parent_data.get("content", ""),
                    stage=clue.get("stage", ""),
                    hop=parent_hop,  # 🔧 使用从 clue 中提取的 hop
                    metadata={
                        "confidence": clue.get("confidence", 0),
                        "relation": clue.get("relation", ""),
                    }
                )

                # 继续 DFS
                visited.add(parent_id)
                path_nodes.append(parent_node)
                path_clues.append(clue)

                dfs(parent_id, path_nodes, path_clues, visited, depth + 1)

                # 回溯
                path_nodes.pop()
                path_clues.pop()
                visited.remove(parent_id)

        # 从 final 线索的 to 节点开始
        to_node = final_clue.get("to", {})
        to_id = to_node.get("id")

        if not to_id:
            return []

        # 初始化：先添加 final event 节点
        initial_node = PathNode(
            id=to_id,
            type=to_node.get("type", "event"),
            content=to_node.get("content", ""),
            stage="rerank",
            hop=0,
        )

        # 从 from 节点开始反推
        from_node = final_clue.get("from", {})
        from_id = from_node.get("id")

        if not from_id:
            return []

        from_path_node = PathNode(
            id=from_id,
            type=from_node.get("type", "entity"),
            content=from_node.get("content", ""),
            stage=final_clue.get("stage", "rerank"),
            hop=from_node.get("hop", 0),
            metadata={
                "confidence": final_clue.get("confidence", 0),
                "relation": final_clue.get("relation", ""),
            }
        )

        # 开始 DFS
        # 🔧 修复：from_id 不应该在初始 visited 中，因为路径可能回到同一个实体
        # 比如：entity_A → event1 → entity_A → query（通过不同的线索回到同一实体是允许的）
        dfs(
            from_id,
            [initial_node, from_path_node],
            [final_clue],
            {to_id},  # 只包含最终事项节点，不包含 from_id
            depth=0,
        )

        return all_paths

    def _deduplicate_lines(self, lines: List[PathLine]) -> List[PathLine]:
        """
        去重：相同节点序列的路径只保留置信度最高的

        Args:
            lines: 路径列表

        Returns:
            去重后的路径列表
        """
        seen: Dict[Tuple[str, ...], PathLine] = {}

        for line in lines:
            # 用节点ID序列作为去重键
            key = tuple(n.id for n in line.nodes)

            if key not in seen or line.total_confidence > seen[key].total_confidence:
                seen[key] = line

        return list(seen.values())

    def _build_entitys_by_hop(self, lines: List[PathLine]) -> Dict[str, List[Dict[str, Any]]]:
        """
        按跳数分组实体（去重）- 从所有线索中提取

        从原始 clues 中提取 Recall 和 Expand 阶段的 final 实体：
        - Recall 阶段：stage='recall', display_level='final', to.type='entity', hop=0
        - Expand 阶段：stage='expand', display_level='final', to.type='entity', hop>=1

        Args:
            lines: 路径列表（实际不使用，改为使用 self.clues）

        Returns:
            {"0": [entity1, entity2, ...], "1": [...], "2": [...]}
            - "0": Recall 召回的 final 实体
            - "1": Expand 第1跳召回的 final 实体
            - "2": Expand 第2跳召回的 final 实体
        """
        # 按跳数分组存储实体（使用 entity_id 去重）
        hop_entities: Dict[int, Dict[str, Dict]] = defaultdict(dict)

        # 从原始 clues 中提取 final 实体
        for clue in self.clues:
            # 只关注 Recall 和 Expand 阶段的 final 线索
            stage = clue.get("stage")
            display_level = clue.get("display_level")

            if display_level != "final":
                continue

            if stage not in ["recall", "expand"]:
                continue

            # 获取 to 节点（目标实体）
            to_node = clue.get("to", {})
            if to_node.get("type") != "entity":
                continue

            entity_id = to_node.get("id")
            hop = to_node.get("hop", 0)

            if not entity_id:
                continue

            # 如果该 entity 在当前 hop 还未记录，则添加
            if entity_id not in hop_entities[hop]:
                hop_entities[hop][entity_id] = {
                    "id": entity_id,
                    "name": to_node.get("content", ""),
                    "type": to_node.get("category", ""),
                    "description": to_node.get("description", ""),
                    "hop": hop,
                    "stage": stage,
                    # 保留完整的原始数据
                    **to_node
                }

        # 转换为字符串键的字典
        result = {}
        for hop in sorted(hop_entities.keys()):
            result[str(hop)] = list(hop_entities[hop].values())

        # 添加统计日志
        if result:
            stats_str = ", ".join([f"hop{h}={len(entities)}" for h, entities in result.items()])
            self.logger.info(f"📊 实体按跳数统计 (从 final 线索提取): {stats_str}")
        else:
            self.logger.warning("⚠️ 未找到任何 final 实体线索")

        return result

    def _extract_min_lines_from_rerank(self, rerank_lines: Dict[str, List[List[Dict[str, Any]]]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        从 rerank_lines 中提取每个事项的最短路径

        Args:
            rerank_lines: {"event-id": [[path1], [path2], ...]}

        Returns:
            {"event-id": [{"query": ...}, {"entity": ...}, {"event": ...}]}
        """
        min_lines = {}

        for event_id, paths in rerank_lines.items():
            if not paths:
                continue

            # 找到最短路径（优先比较长度，其次比较置信度）
            min_path = min(paths, key=lambda p: (len(p), -self._calculate_path_confidence(p)))
            min_lines[event_id] = min_path

        return min_lines

    def _extract_max_lines_from_rerank(self, rerank_lines: Dict[str, List[List[Dict[str, Any]]]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        从 rerank_lines 中提取每个事项的最长路径

        Args:
            rerank_lines: {"event-id": [[path1], [path2], ...]}

        Returns:
            {"event-id": [{"query": ...}, {"entity": ...}, {"event": ...}]}
        """
        max_lines = {}

        for event_id, paths in rerank_lines.items():
            if not paths:
                continue

            # 找到最长路径（优先比较长度，其次比较置信度）
            max_path = max(paths, key=lambda p: (len(p), self._calculate_path_confidence(p)))
            max_lines[event_id] = max_path

        return max_lines

    def _calculate_path_confidence(self, path: List[Dict[str, Any]]) -> float:
        """
        计算路径的置信度（简单取平均，或从 metadata 中获取）

        Args:
            path: [{"query": ...}, {"entity": ...}, {"event": ...}]

        Returns:
            置信度值
        """
        # 从路径节点的 metadata 中提取置信度
        confidences = []
        for node in path:
            for node_type, node_data in node.items():
                if isinstance(node_data, dict):
                    conf = node_data.get("confidence", node_data.get("metadata", {}).get("confidence", 1.0))
                    if conf and conf > 0:
                        confidences.append(conf)

        # 返回平均置信度，如果没有则返回1.0
        return sum(confidences) / len(confidences) if confidences else 1.0

    def _build_event_lines_from_dict(self, event_paths: Dict[str, PathLine]) -> Dict[str, List[Dict[str, Any]]]:
        """
        从事项路径字典构建富含路径信息（可用于最短或最长路径）

        Args:
            event_paths: {"event-id": PathLine}

        Returns:
            {
                "event-id": [
                    {"query": {...}},
                    {"entity": {...}},
                    {"entity": {...}},
                    {"event": {...}}
                ]
            }
        """
        result = {}

        for event_id, line in event_paths.items():
            path_items = []

            for node in line.nodes:
                # 从 self.nodes 获取完整节点信息
                node_data = self.nodes.get(node.id, {})

                if node.type == "query":
                    path_items.append({
                        "query": {
                            "id": node.id,
                            "content": node.content,
                            "type": node_data.get("category", "origin"),
                            # 保留完整数据
                            **node_data
                        }
                    })
                elif node.type == "entity":
                    path_items.append({
                        "entity": {
                            "id": node.id,
                            "name": node.content,
                            "type": node_data.get("category", ""),
                            "description": node_data.get("description", ""),
                            "hop": node.hop,
                            "stage": node.stage,
                            # 保留完整数据
                            **node_data
                        }
                    })
                elif node.type == "event":
                    # 获取完整的 event 信息
                    path_items.append({
                        "event": {
                            "id": node.id,
                            "event_id": node_data.get("event_id", node.id),
                            "title": node.content,
                            "content": node_data.get("description", ""),
                            "category": node_data.get("category", ""),
                            "stage": node.stage,
                            # 保留完整数据
                            **node_data
                        }
                    })

            result[event_id] = path_items

        self.logger.info(f"📋 构建事项路径: {len(result)} 个事项")

        return result

    def _build_all_event_lines(self, all_lines: List[PathLine]) -> Dict[str, List[List[Dict[str, Any]]]]:
        """
        从所有路径构建富含路径信息（每个事项包含所有路径）

        Args:
            all_lines: 所有路径列表

        Returns:
            {
                "event-id": [
                    [{"query": {...}}, {"entity": {...}}, {"event": {...}}],  # 路径1
                    [{"query": {...}}, {"entity": {...}}, {"event": {...}}],  # 路径2
                    ...
                ]
            }
        """
        from collections import defaultdict
        result = defaultdict(list)

        for line in all_lines:
            event_id = line.event_id
            path_items = []

            # 🐛 调试日志：输出路径信息
            entity_hops = [n.hop for n in line.nodes if n.type == "entity"]
            if entity_hops:
                self.logger.debug(
                    f"🛤️ Path for event {event_id[:20]}...: entity hops={entity_hops}"
                )

            for node in line.nodes:
                # 从 self.nodes 获取完整节点信息
                node_data = self.nodes.get(node.id, {})

                if node.type == "query":
                    path_items.append({
                        "query": {
                            "id": node.id,
                            "content": node.content,
                            "type": node_data.get("category", "origin"),
                            # 保留完整数据
                            **node_data
                        }
                    })
                elif node.type == "entity":
                    path_items.append({
                        "entity": {
                            "id": node.id,
                            "name": node.content,
                            "type": node_data.get("category", ""),
                            "description": node_data.get("description", ""),
                            "hop": node.hop,
                            "stage": node.stage,
                            # 保留完整数据
                            **node_data
                        }
                    })
                elif node.type == "event":
                    # 获取完整的 event 信息
                    path_items.append({
                        "event": {
                            "id": node.id,
                            "event_id": node_data.get("event_id", node.id),
                            "title": node.content,
                            "content": node_data.get("description", ""),
                            "category": node_data.get("category", ""),
                            "stage": node.stage,
                            # 保留完整数据
                            **node_data
                        }
                    })

            # 将这条路径添加到对应事项的路径列表中
            result[event_id].append(path_items)

        # 转换为普通字典
        result_dict = dict(result)

        self.logger.info(
            f"📋 构建事项所有路径: {len(result_dict)} 个事项, "
            f"平均每个事项 {sum(len(paths) for paths in result_dict.values()) / len(result_dict):.1f} 条路径"
        )

        return result_dict


def analyze_paths(
    clues: List[Dict[str, Any]],
    target_event_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    便捷函数：分析线索路径

    Args:
        clues: 线索列表
        target_event_ids: 目标事项ID列表（仅分析这些事项的路径）
                         如果为 None，则分析所有 final 线索

    Returns:
        路径分析结果字典
    """
    if not clues:
        return {
            "min_lines": {},
            "max_lines": {},
            "entitys": {},
            "rerank_lines": {},
            "stats": {
                "total_lines": 0,
                "avg_length": 0,
                "avg_confidence": 0,
            },
        }

    analyzer = PathAnalyzer(clues)
    result = analyzer.analyze(target_event_ids=target_event_ids)
    return result.to_dict()


__all__ = [
    "PathAnalyzer",
    "PathAnalysisResult",
    "PathLine",
    "PathNode",
    "analyze_paths",
]
