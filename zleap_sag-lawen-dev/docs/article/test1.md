# PRoH: Dynamic Planning and Reasoning over Knowledge Hypergraphs for Retrieval-Augmented Generation

Xiangjun Zai  
University of New South Wales  
Sydney, Australia  
xiangjun.zai@unsw.edu.au

Qing Liu Data61, CSIRO Sydney, Australia q.liu@data61.csiro.au

Xingyu Tan  
University of New South Wales  
Sydney, Australia  
xingyu.tan@unsw.edu.au

Xiwei Xu  
Data61, CSIRO  
Sydney, Australia  
xiwei.xu@data61.csiro.au

Xiaoyang Wang  
University of New South Wales  
Sydney, Australia  
xiaoyang.wang1@unsw.edu.au

Wenjie Zhang  
University of New South Wales  
Sydney, Australia  
wenjie.zhang@unsw.edu.au

# Abstract

Knowledge Hypergraphs (KHs) have recently emerged as a knowledge representation for retrieval-augmented generation (RAG), offering a paradigm to model multi-entity relations into a structured form. However, existing KH-based RAG methods suffer from three major limitations: static retrieval planning, non-adaptive retrieval execution, and superficial use of KH structure and semantics, which constrain their ability to perform effective multi-hop question answering. To overcome these limitations, we propose PRoH, a dynamic Planning and Reasoning over Knowledge Hypergraphs framework. PRoH incorporates three core innovations: (i) a context-aware planning module that sketches the local KH neighborhood to guide structurally grounded reasoning plan generation; (ii) a structured question decomposition process that organizes subquestions as a dynamically evolving Directed Acyclic Graph (DAG) to enable adaptive, multi-trajectory exploration; and (iii) an Entity-Weighted Overlap (EWO)-guided reasoning path retrieval algorithm that prioritizes semantically coherent hyperedge traversals. Experiments across multiple domains demonstrate that PRoH achieves state-of-the-art performance, surpassing the prior SOTA model HyperGraphRAG by an average of  $19.73\%$  in F1 and  $8.41\%$  in Generation Evaluation (G-E) score, while maintaining strong robustness in long-range multi-hop reasoning tasks.

# ACM Reference Format:

Xiangjun Zai, Xingyu Tan, Xiaoyang Wang, Qing Liu, Xiwei Xu, and Wenjie Zhang. 2018. PRoH: Dynamic Planning and Reasoning over Knowledge Hypergraphs for Retrieval-Augmented Generation. In Proceedings of Make sure to enter the correct conference title from your rights confirmation email (Conference acronym 'XX). ACM, New York, NY, USA, 13 pages. https://doi.org/XXXXXXXX.XXXXXXXXXX

Permission to make digital or hard copies of all or part of this work for personal or classroom use is granted without fee provided that copies are not made or distributed for profit or commercial advantage and that copies bear this notice and the full citation on the first page. Copyrights for components of this work owned by others than the author(s) must be honored. Abstracting with credit is permitted. To copy otherwise, or republish, to post on servers or to redistribute to lists, requires prior specific permission and/or a fee. Request permissions from permissions@acm.org.

Conference acronym 'XX, Woodstock, NY

© 2018 Copyright held by the owner/author(s). Publication rights licensed to ACM.

ACM ISBN 978-1-4503-XXXX-X/18/06

https://doi.org/XXXXXXXXXXXXXXXXXX

# 1 Introduction

To improve the factual accuracy and specificity of large language model (LLM) responses, Retrieval-Augmented Generation (RAG) has emerged as a promising approach that integrates external knowledge through the in-context learning capabilities of LLMs. However, traditional RAG systems rely primarily on semantic similarity, fail to capture the structured relational knowledge inherent in many information domains, and often retrieve redundant or noisy content [25]. To address this limitation, Graph-based RAG has been introduced to integrate explicitly structured representations of knowledge into the retrieval process, enabling more accurate and interpretable reasoning [5, 10-12]. By representing entities and their relationships as Knowledge Graphs (KGs), these approaches can capture indirect relations and support multi-hop reasoning across interconnected facts. Most existing Graph-based RAG frameworks, however, model only relations that involve exactly two entities. This design overlooks a fundamental property of real-world knowledge, which is, many relations are inherently n-ary, involving more than two entities simultaneously. As shown in Figure 1, the relation "Mario + Rabbids Kingdom Battle" is the first major collaboration between Nintendo and Ubisoft." connects three entities: "Mario + Rabbids Kingdom Battle", "Nintendo" and "Ubisoft". In such cases, the semantics of a relation is established only when all participating entities are considered together. Decomposing these n-ary relations into multiple binary edges inevitably causes a loss of critical structural and semantic information [6, 9, 26, 32].

To address the representational gap, Knowledge Hypergraphs (KHs) have been proposed as a more compact and semantically expressive knowledge structure for Graph-based RAG [4, 7, 19, 31]. KHs generalize standard KGs by allowing hyperedges to connect multiple nodes simultaneously, naturally capturing complex multi-entity interactions and preserving n-ary relational semantics more faithfully. As a result, KHs enhance both the storage of knowledge and its retrieval for downstream comprehension tasks. Currently, most KH-based RAG systems follow a three-stage pipeline:  $i$  ) KH construction: extract entities and n-ary relations from the text sources to build the KH; ii) KH-guided retrieval: link query topics with entities and map queries to hyperedges through predefined similarity metrics, followed by a shallow, heuristic-based graph fusion that retrieves graph elements along with their corresponding source text chunks; iii) Answer generation: pass the retrieved

![](images/f0786c0b1dfd6dbe3e8baf7baace516d0591549a39dd98deef713479c6f76f7f.jpg)  
Figure 1: Illustration of Knowledge Hypergraph.

knowledge directly to the generation module. Although this approach has shown promising results in question-answering (QA) tasks, it does not fully exploit the expressive potential of KHis and suffers from the following limitations:

Limitation 1: Static Retrieval Planning. Existing frameworks rely on predefined, hard-coded retrieval pipelines that apply the same sequence of operations regardless of query content or graph context. For example, HGRAG [31] performs a KH diffusion with a fixed number of iterations, without evaluating whether the retrieved passages are sufficient. This rigid design prevents the model from adapting its retrieval plan to the question semantics or the KH topology, leading to inefficient and misaligned knowledge access. Limitation 2: Non-Adaptive Retrieval Execution. Current systems perform retrieval in a one-shot, non-iterative manner, relying solely on the original query. For instance, HyperGraphRAG [19] identifies and retrieves relevant entities and hyperedges based on a predefined similarity threshold in one graph call. Such static execution fails to refine retrieval using intermediate reasoning results, limiting the system's capability for multi-hop reasoning.

Limitation 3: Superficial Use of Graph Structure and Semantics. Existing methods primarily treat hyperedges as simple links or routing mechanisms for accessing associated text chunks [7, 19]. This superficial treatment ignores the rich relational semantics encoded in hyperedges and misses the opportunity to guide more precise retrieval and reasoning within KH-based RAG frameworks.

Contribution. To better realize the potential of KHis for RAG, we introduce PRoH, a dynamic KH-based RAG framework that fully leverages the expressive power of KHis. PRoH is designed to perform structured planning and reasoning directly over KHis, enabling the retriever to adaptively explore, refine, and integrate knowledge

for multi-hop question answering. The key ideas of PRoH can be summarized as follows:

Context aware planning. PRoH employs a graph scope-aware planning strategy. Before performing question decomposition, PRoH first sketches the local neighborhood of the topic entities within the KH. This pre-planning step provides the LLM with a brief yet informative view of the topological and semantic scope of the question-relevant subgraph, mitigating the mismatch between linguistic-only decomposition and the actual graph knowledge available. Consequently, the LLM produces reasoning plans that are more feasible and better aligned with the structure of the underlying KH.

Structured question decomposition with iterative refinement.

PRoH adopts a structured question decomposition approach to explicitly capture the dependencies among subquestions. Instead of treating subquestions as a linear sequence, the reasoning plan is represented as a Directed Acyclic Graph (DAG) that captures logical precedence among them. As reasoning progresses following the topological order of the subquestions, the DAG is iteratively refined. To be more specific, later subquestions are updated, and new subquestions and dependencies may emerge. This mechanism allows the reasoning plan to evolve dynamically and remain consistent with the current reasoning state. PRoH also introduces a state-space search mechanism that performs reasoning as a branching exploration from the current reasoning state, effectively modeling the process as a tree. Unlike prior methods that assume each subquestion has one single correct answer, our approach allows multiple candidate answers per subquestion. That is, several reasoning trajectories can coexist. This design corresponds to the multi-entity nature of n-ary relations, allowing PRoH to manage ambiguity and recover from local errors. The state exploration continues until one or more trajectories reach a goal state, where all subquestions are resolved and a final answer can be derived.

EWO-guided reasoning path retrieval. PRoH employs a fine-grained reasoning path retrieval strategy guided by the Entity-Weighted Overlap (EWO) score, specifically designed for KHS. When visiting a hyperedge, for each hyperedge that overlaps with the current one, the retriever evaluates how strongly the overlapping entities contribute to answering the current subquestion and aggregates these relevance scores to determine the next traversal direction. This process allows the retriever to prioritize semantically meaningful connections rather than relying on purely structural overlaps. As a result, the retrieved reasoning paths are better aligned with the underlying semantics of the question, enabling more accurate and interpretable multi-hop reasoning.

In summary, the main contributions of this paper are as follows:

- We propose PRoH, a dynamic Knowledge Hypergraph-based RAG framework that fully leverages the expressive power of hypergraphs for multi-hop question answering.  
- We introduce a context-aware planning mechanism that sketches the underlying Knowledge Hypergraph and generates feasible reasoning plans.  
- We develop an Entity-Weighted Overlap (EWO)-guided reasoning path retrieval strategy for fine-grained, semantically aware exploration of Knowledge Hypergraphs.  
- PRoH consistently achieves better performance and interpretability than the state-of-the-art HyperGraphRAG framework across

multiple knowledge domains, surpassing it by an average of  $19.73\%$  in F1 and  $8.41\%$  in Generation Evaluation (G-E).

# 2 Related Work

Graph-based RAG. Unlike traditional RAG systems, which rely on flat textual corpora as their primary knowledge source, Graph-based RAG leverages structured representations of relational knowledge. These systems either construct knowledge graphs from documents or utilize existing large-scale graphs such as Wikidata [30] and Freebase [1], enabling more precise retrieval and relation-aware reasoning [13, 25, 35, 40]. EmbedKGQA [27] first introduces KG embedding methods into multi-hop KGQA. Recent representative frameworks [5, 10, 11, 33, 39] extract entities and relations from unstructured text using LLMs and index them for retrieval via graph traversal or embedding-based matching. More advanced approaches [3, 8, 16-18, 22, 23, 28, 29, 37, 38] incorporate iterative reasoning and adaptive planning mechanisms to enhance graph-guided inference. Learning-based methods [14, 15, 20, 21, 24, 34, 36] have also shown promising results. Despite these advances, existing graph-based RAG frameworks remain limited by their binary relational representations, which restrict their capacity to model multi-entity facts and capture higher-order relational semantics.

Knowledge Hypergraph-based RAG. Early systems such as HyperGraphRAG [19] and Hyper-RAG [7] extract hyperedges from textual sources to capture higher-order relations and employ similarity-based retrieval to identify relevant entities, hyperedges, and text chunks for question answering. IdepRAG [4] leverages the hypergraph structure by performing Personalized PageRank over topic entities to locate contextually relevant evidence. Meanwhile, HGRAG [31] introduces a cross-granularity retrieval mechanism that integrates fine-grained entity similarity with coarse-grained passage similarity through hypergraph diffusion, effectively balancing structural precision and semantic coherence. However, current hypergraph-based approaches still rely on heuristic, one-shot retrieval pipelines and lack context-aware and iterative reasoning capabilities, motivating the framework proposed in this study.

# 3 Preliminary

Let  $\mathcal{H} = (\mathcal{V},\mathcal{E})$  denote a knowledge hypergraph, where  $\mathcal{V}$  and  $\mathcal{E}$  represent the set of entities and hyperedges, respectively. Each hyperedge  $e\in \mathcal{E}$  links a sequence of entities in  $\mathcal{V}$ , i.e.,  $V(e) = (v_{1},v_{2}\dots ,v_{n})$  where  $n\geq 1$ . An n-ary relationship fact is modeled as  $f = (e,V(e))$ . We denote the set of hyperedges in  $\mathcal{E}$  that contains the entity  $v$  as  $E(v)$ , i.e.,  $E(u) = \{e|v\in V(e)\land e\in \mathcal{E}\}$ . Given a knowledge hypergraph  $\mathcal{H} = (\mathcal{V},\mathcal{E})$ , a subgraph  $\mathcal{H}_S = (\mathcal{V}_S,\mathcal{E}_S)$  is an induced subgraph of  $\mathcal{H}$ , if  $\mathcal{E}_S\subseteq \mathcal{E}$ ,  $\mathcal{V}_S = \{v|v\in V(e)\land e\in \mathcal{E}_S\}$ . Two hyperedges  $e_i$  and  $e_j$  are considered connected iff  $V(e_i)\cap V(e_j)\neq \emptyset$ , i.e., an overlap of entities exists between  $e_i$  and  $e_j$ . Given a hyperedge  $e$ , the set of hyperedges connected to  $e$  are defined as the neighbor edge set  $\mathrm{Nbr}(e) = \{e^{\prime}\mid V(e^{\prime})\cap V(e)\neq \emptyset \land e^{\prime}\neq e\land e^{\prime}\in \mathcal{E}\}$ .

DEFINITION 1 (HYPERGRAPH-BASED RAG). Given a question  $q$  and a knowledge hypergraph  $\mathcal{H} = (\mathcal{V}, \mathcal{E})$ , hypergraph-based RAG retrieves question-related knowledge, i.e., a set of facts  $\mathcal{F}$  from  $\mathcal{H}$  and then generates an answer  $a(q)$  based on  $q$  and  $\mathcal{F}$ .

DEFINITION 2 (REASONING PATH). Given a knowledge hypergraph  $\mathcal{H} = (\mathcal{V},\mathcal{E})$ , a reasoning path within  $\mathcal{H}$  is defined as a connected sequence of hyperedges, represented as  $\text{path}(e_s,e_t) = [e_1 = e_s,e_2,\dots ,e_{l - 1},e_l = e_t]$ , where  $l$  denotes the length of the path, i.e.,  $l = | \text{path}(e_s,e_t) |$ .

# 4 Method

In this section, we introduce the framework of PRoH. Compared to previous approaches, our model focuses on solving multi-hop questions based on KHis by generating and dynamically refining reasoning plans that consist of subquestions of the original question, and retrieving knowledge guided by reasoning paths in the KHis. The framework of PRoH consists of four main components. We outline its workflow in Figure 2.

# 4.1 Graph Construction and Indexing

KH Construction. We adopt the graph construction method introduced in HyperGraphRAG [19]. Given the documents  $K$ , the method first extracts hyperedges from text chunks, then identifies entities within these hyperedges, and finally constructs the KH  $\mathcal{H} = (\mathcal{V}, \mathcal{E})$ . Each entity  $v \in \mathcal{V}$  and hyperedge  $e \in \mathcal{E}$  is identified by its name  $v^{nm}$  or  $e^{nm}$ , respectively. Each entity is associated with a textual description  $v^{desc}$ , while each hyperedge  $e$  maintains a reference  $e^{ref}$  to the text chunk that it originates from. For efficient retrieval, vector databases are maintained for entity names, entity descriptions, and hyperedge names.

Synonym Hyperedge Augmentation. In the original method [19], entity de-duplication relies on exact name matching, which results in isolated hyperedges and weakens the connectivity of the constructed KH. To better utilize graph structure in the later retrieval stage, inspired by HippoRAG2 [12], we introduce synonym hyperedges to the constructed KH. To be more specific, the synonym hyperedges are augmented in three steps. First, for each pair of entities  $(v_{i}, v_{j}) \in \mathcal{V} \times \mathcal{V}$ , we compute the cosine similarity

$$
\operatorname {s i m} \left(v _ {i}, v _ {j}\right) = \cos \left(\mathbf {z} \left(v _ {i} ^ {\mathrm {n m}}\right), \mathbf {z} \left(v _ {j} ^ {\mathrm {n m}}\right)\right), \tag {1}
$$

where  $\mathbf{z}(\cdot)$  denotes the embedding function. We add a similarity edge  $e_{sim} = (v_i, v_j)$  if  $s(v_i, v_j) \geq \tau$ . Second, we form the similarity subgraph  $\mathcal{H}_{sim} = (\mathcal{V}_{sim}, \mathcal{E}_{sim})$  and compute its connected components  $\{C_1, C_2, \ldots, C_m\}$ , where each  $C_i \subseteq \mathcal{V}_{sim}$ . Third, for each connected component  $C_i$ , we query an LLM with the entity descriptions  $\{v^{desc} \mid v \in C_i\}$  to determine whether they represent synonymous entities. If the set of synonymous entities  $V_{syn} \subseteq C_i$  is confirmed, we add a synonym hyperedge  $e_{syn}$  which links all entities in  $V_{syn}$ .

# 4.2 Graph Anchoring

Topic Entity Identification. Given a question  $q$ , we first utilize an LLM to extract a set of keywords  $T_{w}$ . Each keyword is then linked to candidate entities in  $\mathcal{V}$  by computing cosine similarity scores as defined in (1). The highest-scoring candidates above a similarity threshold  $\theta_{v}$  are collected to form the topic entity set  $\mathcal{T}$ .

Target Hyperedge Matching. To exploit the semantic information contained in the question  $q$ , we also retrieve related hyperedges

![](images/122021976038bb06a8c908f639454a04df4dbb0dd7ee627d639ea4be75e8b5f0.jpg)  
Figure 2: An overview architecture of PRoH. Given the input question and KH, the workflow begins with Graph Anchoring (green) and constructs a question subgraph. The following Plan Initialization Module (purple) sketches the question subgraph and obtains context to generate initial reasoning plans and constructs reasoning DAGs for the question. Those DAGs serve as roots of the state search trees in the Reasoning stage (gray). At each state within the State Search Tree, the model retrieves answer-path pairs from the KH and then iteratively completes and refines the DAGs to transit into the next state until one or more DAGs are completed. These completed DAGs are then passed to the final answer generation stage (yellow) as the retrieved knowledge for producing the final answer.

from  $\mathcal{E}$ . For each hyperedge, we compute a similarity score between  $q$  and the hyperedge name, following a formulation analogous to the cosine similarity in (1). The top-ranked hyperedges that satisfy the threshold  $\theta_{e}$  form the target hyperedge set  $\mathcal{R}$ .

Question Subgraph Construction. Once the topic entities  $\mathcal{T}$  and target hyperedges  $\mathcal{R}$  are identified, we construct a question subgraph to constrain subsequent retrieval during planning and reasoning. Specifically, for each  $v\in \mathcal{T}$  and  $e\in \mathcal{R}$ , we extract its  $D_{\mathrm{max}}$ -hop neighborhood from  $\mathcal{H} = (\mathcal{V},\mathcal{E})$ . The question subgraph  $\mathcal{H}_q$  is defined as the union of these neighborhoods. We also merge synonymous entities during this subgraph construction phase to obtain a compact representation of the original KH, which benefits the subsequent planning and reasoning.

# 4.3 Reasoning Plan Initialization

For multi-hop questions, directly retrieving graph elements from the immediate neighborhood of topic entities or target hyperedges is often insufficient. However, naively expanding to deeper neighborhoods quickly leads to an information explosion, as the number of reachable entities and hyperedges grows exponentially with depth. This effect is particularly critical in hypergraphs, where nary relations link multiple entities within one single hyperedge, allowing one hyperedge to connect to many hyperedges and thereby rapidly increasing the branching width of the search. Therefore, to control the knowledge retrieval process and selectively retrieve only the most relevant and necessary knowledge from the KH, we introduce the concept of reasoning plans.

DEFINITION 3 (REASONING PLAN). Given a question  $q$ , a reasoning plan is a structured decomposition of  $q$  represented as a pair  $(Q, \mathcal{L})$ . Here,  $Q = \{q_1, q_2, \dots, q_m\}$  denotes the set of subquestions, where each

$q_{i}$  addresses a partial aspect of  $q$ , and  $\mathcal{L} \subseteq \mathcal{Q} \times \mathcal{Q}$  encodes dependency constraints among them. The relation  $\mathcal{L}$  defines a partial order, that is, if  $(q_{i}, q_{j}) \in \mathcal{L}$ , then  $q_{i}$  must be answered before  $q_{j}$ .

Question Subgraph Sketching. While it is possible to generate reasoning plans directly from the internal knowledge of an LLM, such plans are often misaligned with the underlying KH. In particular, the LLM may introduce subquestions that cannot be resolved because it lacks awareness of domain-specific relations. Moreover, it is not sufficient to rely solely on the anchored graph elements, i.e., topic entities  $\mathcal{T}$  and target hyperedges  $\mathcal{R}$ , since these elements alone do not reflect the broader relational structure which is critical for multi-hop reasoning. To mitigate this issue, we construct a plan context graph that efficiently sketches the structure of the hypergraph. This is achieved by treating topic entities and target hyperedges as seeds for controlled exploration. The resulting subgraph provides explicit grounding for plan generation and improves the alignment between the reasoning plan and the available knowledge.

DEFINITION 4 (PLAN CONTEXT GRAPH). Given a question  $q$ , a KH  $\mathcal{H} = (\mathcal{V},\mathcal{E})$ , the question subgraph  $\mathcal{H}_q = (\mathcal{V}_q,\mathcal{E}_q)$ , topic entity set  $\mathcal{T}\subseteq \mathcal{V}$ , target hyperedge set  $\mathcal{R}\subseteq \mathcal{E}$ , and a plan depth  $d_p$ , the plan context graph  $\mathcal{H}_p = (\mathcal{V}_p,\mathcal{E}_p)$  is defined as a subgraph of  $\mathcal{H}$ , where  $\mathcal{V}_p$  and  $\mathcal{E}_p$  include entities and hyperedges that are highly relevant to  $q$  and are within the  $d_p$ -hop neighborhood of either  $\mathcal{T}$  or  $\mathcal{R}$ .

We initialize the plan graph  $\mathcal{H}_p = (\mathcal{V}_p, \mathcal{E}_p)$  using target hyperedges  $\mathcal{R}$  and the hyperedges incident to the topic entities  $\mathcal{T}$ . These hyperedges also serve as the initial frontier for exploration. To guide the search direction, we employ a hyperedge scoring strategy. For each frontier hyperedge  $e$ , we first compute entity-level relevance scores for all entities  $v \in e$  with respect to the question  $q$ , using a

function on its description and the question:

$$
\operatorname {S E} (v \mid q) = \cos \left(\mathbf {z} (v ^ {\text {d e s c}}), \mathbf {z} (q)\right), \tag {2}
$$

where  $\mathbf{z}(\cdot)$  denotes the embedding function. For each neighboring hyperedge  $e' \in \mathrm{Nbr}(e)$ , we then aggregate the scores of the overlapping entities  $V(e) \cap V(e')$  to obtain an hyperedge-level relevance score with respect to  $q$  and  $e$ :

$$
\mathrm {S H} \left(e ^ {\prime} \mid q, e\right) = \text {A g g r e g a t e} \left(\left\{\mathrm {S E} (v, q) \mid v \in V (e) \cap V \left(e ^ {\prime}\right) \right\}\right). \tag {3}
$$

Based on the hyperedge-level relevance scores, low-scoring directions (hyperedges) are pruned, and the exploration will focus on directions that are supported by highly relevant entities.

Initial Reasoning Plan Generation. After constructing the plan context graph  $\mathcal{H}_p$ , we leverage it as a structured input for the LLM to propose reasoning plans. We transfer the graph structure into a natural language plan context by augmenting the hyperedges layer by layer, from the nearest neighborhood of the anchored graph elements to the more distant neighborhoods. This ensures that the context reflects local relevance and progressively broader structural information. Formally, given the plan context graph  $\mathcal{H}_p$ , the plan context  $c_p$  is defined as  $c_p = \text{FormPlanContext}(\mathcal{H}_p, \mathcal{T}, \mathcal{R})$ , where  $\text{FormPlanContext}$  denotes the procedure that extracts and formats the relevant subgraph structure into plan context. The LLM is then prompted with the question  $q$ , the topic entities  $\mathcal{T}$ , and the plan context  $c_p$  to generate initial reasoning plans.

Initial Reasoning DAG construction. Given a reasoning plan  $(Q, \mathcal{L})$ , the dependency relation  $\mathcal{L}$  may contain transitive edges. To obtain a minimal representation, we apply a Hasse Reduction that removes all dependency relations that can be transitively covered. That is, if  $(q_i, q_j) \in \mathcal{L}$  and there exists  $q_k \in Q$  such that  $(q_i, q_k) \in \mathcal{L}$  and  $(q_k, q_j) \in \mathcal{L}$ , then  $(q_i, q_j)$  is considered redundant and excluded from  $\mathcal{L}_H$ . The reduced relation  $\mathcal{L}_H$  captures only the immediate dependencies between subquestions.

DEFINITION 5 (REASONING DAG). A reasoning DAG is the graph abstraction of a reasoning plan  $(Q, \mathcal{L})$ . It is defined as a directed acyclic graph (DAG)  $D = (Q, \mathcal{L}_H)$ , where each node represents a subquestion  $q_i \in Q$  and each directed edge  $(q_i, q_j) \in \mathcal{L}_H$  encodes the immediate dependency between  $q_i$  and  $q_j$ .

For each reasoning plan, we construct a corresponding reasoning DAG. We then apply a topological sort on the reduced dependency relation  $\mathcal{L}_H$  to obtain an execution order over the subquestions. This order will guide the level-by-level completion of the reasoning DAG. The processed reasoning DAGs are collected to form the initial reasoning DAG set  $\mathcal{D}_0$ . Due to space limitations, the pseudo-code of the plan initialization algorithm is provided in Appendix A.1.

# 4.4 Reasoning

Once the initial reasoning DAGs are constructed, the next step is to query the KH under their guidance. More specifically, for a reasoning DAG  $D$ , questions at the first level without dependencies are resolved first. The retrieved answers are used to refine the  $D$  and the questions of the next level will be unlocked for reasoning. This iterative process repeats until all subquestions are answered. The step answers to subquestions and supporting knowledge are

stored in the completed reasoning DAG. We refer to this process of progressively resolving and refining DAGs as reasoning. Due to space limitations, the pseudo-code of the reasoning algorithm is provided in Appendix A.2.

DEFINITION 6 (COMPLETED REASONING DAG). A completed reasoning DAG is defined as a DAG  $D_{\mathrm{comp}} = (Q, \mathcal{L}_H, \mathcal{AP})$ , where each node  $q_j \in Q$  is associated with a non-empty set of answer-path pairs  $\mathcal{AP}[q_j] = \{(a_j, p_j)\}$ . Here,  $a_j$  is a candidate answer to  $q_j$  and  $p_j$  is a supporting reasoning path in  $\mathcal{H}_q$ .

Reasoning as State-Space Search. The aforementioned reasoning process can be viewed as a structured search problem over DAG states. A reasoning state represents a partially completed reasoning DAG. It captures both the current reasoning DAG and the current progress in resolving its subquestions. The initial state corresponds to an initial reasoning DAG  $D \in \mathcal{D}_0$  with no subquestions resolved. The goal state is a completed reasoning DAG. Formally, we define a reasoning state as follows.

DEFINITION 7 (REASONING STATE). A reasoning state is a pair  $(D,i)$ , where  $D = (Q,\mathcal{L}_H,\mathcal{AP})$  is a reasoning DAG and  $i$  is the index of the current reasoning level. A transition from  $(D,i)$  to  $(D',i + 1)$  occurs once all subquestions in the  $i$ -th level of  $D$ , denoted as  $\mathcal{Q}_i$ , are resolved with non-empty sets of answer-path pairs  $\mathcal{AP}_i$ .

Now, we formulate the reasoning process as a search over states and perform it using Depth-First Search (DFS). The frontier  $\mathcal{F}$  is initialized with the set of initial reasoning DAGs  $\mathcal{D}_0$ . At each iteration, a state  $(D,i)$  is popped from  $\mathcal{F}$ . If  $D$  is incomplete, the subquestions  $Q_{i}$  at the current level  $i$  are attempted. Each subquestion is resolved by retrieving reasoning paths from the anchored graph elements in the query subgraph  $\mathcal{H}_q$ , within a KH exploration depth limit  $d_{max}$ . Details of the retrieval procedure are given in the following subsection. The retrieved answer-path pairs are then used to generate successor states. These successor states are pushed back into the frontier for later iterations. If  $D$  is complete, it is added to the solution set  $\mathcal{D}$  comp. The search terminates once  $|\mathcal{D}_{\mathrm{comp}}| \geq K$  or the frontier is empty. Formally, the search procedure is summarized as  $\mathcal{D}_{\mathrm{comp}} = \text{Reasoning}(\mathcal{D}_0, \mathcal{H}_q, d_{\max}, K)$ .

State Transitions. Given a state  $(D,i)$ , the sets of answer-path pairs  $\mathcal{AP}_i$  at level  $i$ , we illustrate the state transition process as follows. Since each subquestion  $q_{j} \in Q_{i}$  is associated with a set of candidate assignments in the form of answer-path pairs  $AP_{j}$ , a valid joint assignment for level  $i$  can be obtained by selecting one answer-path pair  $(a_{j},p_{j}) \in AP_{j}$  for every  $q_{j} \in Q_{i}$ . If multiple joint assignments exist, the current state branches accordingly. For each joint assignment  $\mathbb{AP}$ , a successor reasoning DAG is constructed as  $D_{\mathrm{new}} = \mathrm{LLMGenerateNewDAG}(D,\mathbb{AP})$ . Here, the LLM is prompted with the current set of subquestions  $Q$  together with one candidate answer for each completed subquestion. A refined reasoning plan is proposed by the LLM, which is then validated against the existing reasoning DAG  $D$ , and then merged with  $D$  to produce the successor reasoning DAG  $D_{\mathrm{new}}$ .

# 4.5 Answer and Path Retrieval

The core subroutine for resolving subquestions is the retrieval of answer-path pairs from the question subgraph  $\mathcal{H}_q = (\mathcal{V}_q, \mathcal{E}_q)$ .

We employ an iterative deepening beam search that progressively explores  $\mathcal{H}_q$ . At each depth level, the subquestion is attempted using the knowledge retrieved based on a reasoning path discovered so far. The process terminates once a reasoning path provides sufficient knowledge to answer the subquestion. Due to space limitations, we detail the algorithm of answer and path retrieval in Appendix A.3.

Graph Re-anchoring. For a subquestion  $q_{j}$ , the relevant knowledge should be within a more concise subregion of the question subgraph  $\mathcal{H}_q$ , where the topic entities  $\mathcal{T}$  and target hyperedges  $\mathcal{R}$  of the original question provide weaker guidance for the search. To account for this, we re-anchor the graph by identifying the topic entities  $\mathcal{T}_j$  and target hyperedges  $\mathcal{R}_j$  specific to  $q_{j}$ , following the same procedure described in Section 4.2. These graph elements serve as seeds for the subsequent beam search, constraining the exploration of  $\mathcal{H}_q$  to the regions most relevant to  $q_{j}$ . Based on  $\mathcal{T}_j$  and  $\mathcal{R}_j$ , we initialize the search frontier  $\mathcal{F}_e$  with the target hyperedges  $\mathcal{R}_j$  and the hyperedges incident to the topic entities  $\mathcal{T}_j$ . The key challenge is then to guide the search toward discovering knowledge most relevant to the question  $q_{j}$ . To address this challenge, we design a strategy tailored to KHS.

EWO-based Search Direction Selection. In standard graphs, two adjacent edges can share at most a single node, in contrast, hyperedges in a hypergraph may overlap on multiple entities. Moreover, the contribution of these overlapping entities to answering a question is not uniform: some are irrelevant, while others provide critical evidence. Thus, neighboring hyperedges should neither be treated as equally relevant only because an overlap exists, nor should their relevance be determined solely by the number of shared entities. To address this, we propose the Entity-Weighted Overlap (EWO) score, a fine-grained strategy in which the relevance of a hyperedge is computed by aggregating the question-specific relevance of its overlapping entities. We now detail the 2-step computation of the EWO score.

Entity scoring. Each overlapping entity  $v \in V(e) \cap V(e')$  is first assigned a provisional relevance score with respect to  $q_j$  using the embedding-based similarity defined in (2). Entities with similarity scores above the threshold  $\theta_{\mathrm{emb}}$  are retained and further evaluated by the LLM to obtain a finer-grained relevance score. Entities with similarity scores below the threshold  $\theta_{\mathrm{emb}}$  are assigned a relevance score of 0. This score reflects how semantically relevant  $v$  is for  $q_j$ .

$$
\operatorname {E W} (v \mid q _ {j}) = \left\{ \begin{array}{l l} \text {L L M S c o r e} (v, q _ {j}), & \text {i f} \operatorname {S E} (v \mid q _ {j}) \geq \theta_ {\text {e m b}}, \\ 0, & \text {o t h e r w i s e .} \end{array} \right. \tag {4}
$$

Hyperedge scoring. Entity scores are then aggregated to produce a hyperedge-level score for each neighbor  $e'$ . This score reflects how semantically relevant  $e'$  is as a potential bridge for a partial reasoning path to answering  $q_j$ .

$$
\operatorname {E W O} \left(e ^ {\prime} \mid q, e\right) = \text {A g g r e g a t e} \left(\left\{S E (v, q) \mid v \in V (e) \cap V \left(e ^ {\prime}\right) \right\}\right). \tag {5}
$$

With the EWO score, we now determine where to expand the search within the candidate search directions (partial reasoning paths)  $F_{\mathrm{cand}}$ . In the first stage,  $F_{\mathrm{cand}}$  is ordered according to the hyperedge-level EWO scores. From the resulting top-ranked directions, we then apply an LLM-based selection function to select the top- $b$  directions:  $F_{\mathrm{sel}} = \text{LLMSELECTDIRECTIONS}(F_{\mathrm{cand}}, q_j, b)$ . This evaluates

the partial reasoning paths in context, rather than relying solely on the EWO score of the terminal hyperedge.

Reasoning Path Selection. At each depth, we construct a set of candidate reasoning paths  $P_{\mathrm{cand}}$  from the partial paths  $\mathcal{P}$  explored so far. Each candidate reasoning path is then ranked using a path-level relevance score that aggregates the EW scores of entities along the path. Formally, the path-level score is defined as:

$$
\operatorname {S P} (p) = \text {A g g r e g a t e} \left(\left\{\operatorname {E W} \left(v \mid q _ {j}\right) \mid v \in e \wedge e \in p \right\}\right). \tag {6}
$$

The top-ranked candidate reasoning paths are then passed to the LLM, to determine whether one or more of them provide sufficient knowledge to yield a step answer for  $q_{j}$ :  $P_{\mathrm{sel}} = \text{LLMSELECTPATHS}(P_{\mathrm{cand}}, q_{j})$ .

Step Answer for Subquestion. If  $P_{\mathrm{sel}}$  contains valid reasoning paths, we attempt to answer subquestion  $q_j$ . For each selected path  $p_j$ , besides the path itself, we also retrieve the descriptions of the entities covered by the path, and, following existing work, the text chunks from which the hyperedges originate. These three components together form the context for  $q_j$ , which is then provided to the LLM to produce a step answer  $a_j$ :  $a_j = \text{LLMAnswerSTEP}(p_j, q_j)$ . The answer and path retrieval procedure terminates once  $P_{\mathrm{sel}}$  has been fully processed, and no further exploration beyond the current depth will be performed.

# 4.6 Final Answer Generation

As discussed in Section 4.4, the reasoning module produces a solution set  $\mathcal{D}_{\mathrm{comp}}$ , where multiple reasoning plans (DAGs) are executed to completion and all sub-questions within those plans are answered. For each completed DAG  $D_{\mathrm{comp}} = (Q, \mathcal{L}_H, \mathcal{AP})$ , our system aggregates the retrieved knowledge along its reasoning process following  $\mathcal{L}_H$  and uses this aggregated knowledge to generate a candidate answer  $a(q)$  to the original question  $q$ . Since different reasoning plans may yield redundant or overlapping answers, we introduce an LLM-based evaluation agent that acts as a judge to aggregate and assess these candidate answers  $\mathcal{A}(q)$ . This judge evaluates each candidate answer  $a(q)$  according to its consistency with the corresponding reasoning path, ultimately selecting the top-ranked answer as the final answer  $a^*(q)$ .

# 5 Experiments

Experimental Settings. We evaluate PRoH on the KHQA datasets introduced in HyperGraphRAG [19], which span five knowledge domains: Medicine, Agriculture, CS, Legal, and Mix. Since the questions in the KHQA datasets are constructed from sampled knowledge fragments located only 1-3 hops away. We further extend these datasets with long-range questions to better assess the multi-hop reasoning capability of PRoH. Specifically, we generate 200 additional questions per domain using knowledge fragments 3-6 hops away. We also develop and evaluate PRoH-L, a variant of PRoH that employs a fully embedding-based EWO score and uses only the hyperedges along the reasoning paths as context for answer generation. Following [19], we adopt three evaluation metrics: F1, Retrieval Similarity (R-S), and Generation Evaluation (G-E). Due to the space limitation, experiment details, including baselines and implementation details, are provided in Appendix B.

Table 1: Results of PRoH across different domains, compared with the state-of-the-art (SOTA). Bold denotes the best performance and underline denotes the runner-up.  

<table><tr><td rowspan="2">Method</td><td colspan="3">Medicine</td><td colspan="3">Agriculture</td><td colspan="3">CS</td><td colspan="3">Legal</td><td colspan="3">Mix</td></tr><tr><td>F1</td><td>R-S</td><td>G-E</td><td>F1</td><td>R-S</td><td>G-E</td><td>F1</td><td>R-S</td><td>G-E</td><td>F1</td><td>R-S</td><td>G-E</td><td>F1</td><td>R-S</td><td>G-E</td></tr><tr><td>LLM-only</td><td>12.89</td><td>0</td><td>43.27</td><td>12.74</td><td>0</td><td>46.85</td><td>18.65</td><td>0</td><td>48.87</td><td>21.64</td><td>0</td><td>49.05</td><td>16.93</td><td>0</td><td>45.65</td></tr><tr><td>StandardRAG</td><td>27.90</td><td>62.57</td><td>55.66</td><td>27.43</td><td>45.81</td><td>57.10</td><td>28.93</td><td>48.40</td><td>56.89</td><td>37.34</td><td>51.68</td><td>59.97</td><td>43.20</td><td>47.26</td><td>64.62</td></tr><tr><td>PathRAG</td><td>14.94</td><td>53.19</td><td>44.06</td><td>21.30</td><td>42.37</td><td>52.48</td><td>26.73</td><td>41.89</td><td>54.13</td><td>31.29</td><td>44.03</td><td>55.36</td><td>37.07</td><td>33.73</td><td>59.11</td></tr><tr><td>HippoRAG2</td><td>21.34</td><td>59.52</td><td>49.57</td><td>12.63</td><td>18.58</td><td>44.85</td><td>17.34</td><td>23.99</td><td>47.87</td><td>18.53</td><td>34.42</td><td>45.93</td><td>21.53</td><td>18.42</td><td>46.35</td></tr><tr><td>HyperGraphRAG</td><td>35.35</td><td>70.19</td><td>59.35</td><td>33.89</td><td>62.27</td><td>59.79</td><td>31.30</td><td>60.09</td><td>57.94</td><td>43.81</td><td>60.47</td><td>63.61</td><td>48.71</td><td>68.21</td><td>66.90</td></tr><tr><td>PRoH-L</td><td>45.63</td><td>70.84</td><td>59.90</td><td>50.47</td><td>64.28</td><td>63.13</td><td>46.61</td><td>60.79</td><td>60.17</td><td>51.40</td><td>64.58</td><td>63.71</td><td>53.81</td><td>59.32</td><td>61.32</td></tr><tr><td>PRoH</td><td>52.94</td><td>74.02</td><td>67.35</td><td>56.67</td><td>58.88</td><td>69.46</td><td>54.15</td><td>57.72</td><td>66.79</td><td>58.81</td><td>65.22</td><td>69.88</td><td>69.16</td><td>59.86</td><td>76.17</td></tr></table>

Table 2: Ablation study results (F1).  

<table><tr><td>Method</td><td>Agriculture</td><td>CS</td><td>Mix</td></tr><tr><td>PRoH</td><td>58.49</td><td>59.47</td><td>69.39</td></tr><tr><td>w/o EWO Guide</td><td>53.22</td><td>56.27</td><td>65.63</td></tr><tr><td>w/o Synonym Merge</td><td>53.26</td><td>54.96</td><td>64.74</td></tr><tr><td>w/o Plan Context</td><td>53.70</td><td>53.67</td><td>64.59</td></tr><tr><td>w/o SrcChunks</td><td>53.55</td><td>54.75</td><td>63.76</td></tr><tr><td>w/o Target Hyperedge</td><td>53.27</td><td>55.60</td><td>60.81</td></tr><tr><td>w/o ALL</td><td>51.93</td><td>51.96</td><td>55.84</td></tr></table>

# 5.1 Main Results

(RQ1) Does PRoH outperform other methods? As shown in Table 1, PRoH achieves state-of-the-art performance across all domains in terms of F1 and G-E scores, outperforming the previous SOTA baseline HyperGraphRAG by an average of  $19.73\%$  and up to  $22.85\%$  in F1 on the CS domain, as well as by an average of  $8.41\%$  and up to  $9.67\%$  in G-E. For the R-S score, PRoH generally achieves comparable results to HyperGraphRAG, with up to a  $4.75\%$  improvement in the Legal domain. The main weakness appears in the Mix domain, which is reasonable since it integrates knowledge from multiple domains. Unlike HyperGraphRAG, which prioritizes retrieving text with high semantic similarity, PRoH retrieves knowledge that contributes directly to reasoning toward the answer—even when such knowledge is not semantically similar to the surface context. Notably, the Mix domain is also where PathRAG, another reasoning-path-based retrieval method, attains its lowest R-S score, indicating a similar behavior pattern. For the variant PRoH-L, it surpasses HyperGraphRAG by an average of  $10.97\%$  and up to  $16.58\%$  in F1 on the Agriculture domain. It also remains competitive with HyperGraphRAG in terms of both G-E and R-S scores, showing up to a  $3.34\%$  improvement in the Agriculture domain and a  $4.11\%$  improvement in the Legal domain, respectively.

# 5.2 Ablation Study

(RQ2) Does the main component of PRoH work effectively? As shown in Table 2, we conduct an ablation study across three domains to quantify the contribution of each module. From each domain, Agriculture, CS and Mix, we randomly sample 200 questions and report the F1 score for comparison. The results show that removing the EWO Guide Direction Selection decreases F1 by up to

Table 3: #Token per Question across Domains.  

<table><tr><td>Domain</td><td>HyperGraphRAG</td><td>PRoH-L</td><td>#Token%↓</td><td>F1↑</td></tr><tr><td>Medicine</td><td>21,112</td><td>19,732</td><td>6.54%</td><td>10.28</td></tr><tr><td>Agriculture</td><td>17,914</td><td>12,528</td><td>30.07%</td><td>16.58</td></tr><tr><td>CS</td><td>18,666</td><td>12,166</td><td>34.82%</td><td>15.31</td></tr><tr><td>Legal</td><td>22,086</td><td>28,831</td><td>-30.54%</td><td>7.59</td></tr><tr><td>Mix</td><td>13,856</td><td>9,687</td><td>30.09%</td><td>5.10</td></tr></table>

![](images/15d1816d389960c3105e3132edc8267bd67bfe2b46de17c07efd70d3b2cb9016.jpg)  
(a) F1 & G-E vs.  $d_{\mathrm{max}}$

![](images/998e01d970008152bb244f07b74500cffdcf71a9c989eb342c484632ded5def8.jpg)  
Figure 3: Impact of depth limit  $d_{\mathrm{max}}$  on performance.  
(b)  $d_{avg}$  vs.  $d_{\max}$

$5.3\%$ , showing its effectiveness in guiding the reasoning path search based on semantic flow from one hyperedge to another. Removing Synonym Merge reduces F1 by up to  $5.2\%$ , indicating that this graph reduction technique benefits the planning and reasoning. Excluding Plan Context leads to a reduction of up to  $5.8\%$ , confirming that context for planning improves the feasibility and alignment of the initial reasoning plan. Without Source Chunks, F1 declines by up to  $5.6\%$ , suggesting that the source text provides additional context that contributes to more accurate answers. Eliminating Target Hyperedge Matching in graph anchoring yields the largest drop, up to  $8.6\%$ , demonstrating the importance of leveraging semantics encoded in hyperedges. When all modules mentioned above are removed (w/o ALL), performance drops sharply by up to  $13.6\%$ , indicating their complementary contributions.

(RQ3) How does the KH exploration depth affect the performance of PRoH? PRoH performs dynamic exploration on KH within the depth limit  $d_{\mathrm{max}}$ . To assess the impact of  $d_{\mathrm{max}}$  on performance, we conducted experiments on 200 randomly sampled questions from the CS domain. We vary  $d_{\mathrm{max}}$  from 2 to 5 and report the corresponding F1 and G-E scores in Figure 3(a). We also collect the actual exploration depth when the step answer for each

Table 4: Performance of PRoH and baselines on long-range Multi-hop QA tasks across domains. Bold denotes the best performance and underline denotes the runner-up.  

<table><tr><td rowspan="2">Method</td><td colspan="3">Medicine</td><td colspan="3">Agriculture</td><td colspan="3">CS</td><td colspan="3">Legal</td><td colspan="3">Mix</td></tr><tr><td>F1</td><td>R-S</td><td>G-E</td><td>F1</td><td>R-S</td><td>G-E</td><td>F1</td><td>R-S</td><td>G-E</td><td>F1</td><td>R-S</td><td>G-E</td><td>F1</td><td>R-S</td><td>G-E</td></tr><tr><td>IO (LLM-only)</td><td>23.36</td><td>0</td><td>0</td><td>30.95</td><td>0</td><td>0</td><td>39.27</td><td>0</td><td>0</td><td>43.20</td><td>0</td><td>0</td><td>48.98</td><td>0</td><td>0</td></tr><tr><td>COT (LLM-only)</td><td>22.70</td><td>0</td><td>43.42</td><td>34.32</td><td>0</td><td>52.22</td><td>42.41</td><td>0</td><td>58.16</td><td>43.36</td><td>0</td><td>57.71</td><td>50.48</td><td>0</td><td>62.24</td></tr><tr><td>SC (LLM-only)</td><td>26.06</td><td>0</td><td>44.80</td><td>37.49</td><td>0</td><td>53.84</td><td>46.42</td><td>0</td><td>60.34</td><td>40.59</td><td>0</td><td>55.36</td><td>54.04</td><td>0</td><td>63.16</td></tr><tr><td>StandardRAG</td><td>21.90</td><td>66.02</td><td>50.13</td><td>48.00</td><td>50.92</td><td>67.81</td><td>27.34</td><td>59.42</td><td>57.11</td><td>35.86</td><td>55.25</td><td>60.37</td><td>52.20</td><td>59.79</td><td>69.91</td></tr><tr><td>HyperGraphRAG</td><td>39.94</td><td>71.72</td><td>60.81</td><td>52.40</td><td>64.36</td><td>70.76</td><td>29.95</td><td>68.78</td><td>58.72</td><td>38.45</td><td>58.30</td><td>61.87</td><td>64.55</td><td>70.23</td><td>76.63</td></tr><tr><td>PRoH-L</td><td>47.30</td><td>71.24</td><td>60.98</td><td>70.02</td><td>65.75</td><td>74.44</td><td>62.11</td><td>65.09</td><td>69.08</td><td>60.25</td><td>59.21</td><td>67.78</td><td>61.19</td><td>62.48</td><td>66.16</td></tr><tr><td>PRoH</td><td>51.26</td><td>75.11</td><td>65.23</td><td>81.01</td><td>62.22</td><td>84.18</td><td>74.83</td><td>68.44</td><td>80.00</td><td>71.93</td><td>64.89</td><td>77.68</td><td>79.69</td><td>68.45</td><td>82.25</td></tr></table>

![](images/fab2851cba2d0180dd96314844d2f0e2d23c267e85ae42958c1a23107538f831.jpg)  
Figure 4: F1 score vs. length of ground-truth context.

![](images/50f3152bb50032b0b8cd374b366e126e0a21cdf269697271a0ed1b359f7583c7.jpg)  
Figure 5: F1 score vs. #entities in ground-truth context.

subquestion is found and the exploration terminates. As shown in Figure 3(a), increasing  $d_{\mathrm{max}}$  initially improves both F1 and G-E scores, with performance peaking at  $d_{\mathrm{max}} = 3$ . Beyond this depth, a deeper search even introduces a slight degradation in both metrics. This suggests that the additional search depth does not uncover additional useful information and instead introduces redundant context that fails to improve reasoning quality.

The trend in the actual exploration depth supports this interpretation. As  $d_{\mathrm{max}}$  increases from 2 to 5, the average actual depth  $d_{\mathrm{avg}}$  grows modestly from 1.41 (at  $d_{\mathrm{max}} = 2$ ) to 2.30 (at  $d_{\mathrm{max}} = 5$ ). This indicates that PRoH rarely needs to utilize the full depth budget; most subquestions are resolved within a relatively short reasoning path. This behavior may have two main reasons. i) PRoH decomposes questions and dynamically refines its reasoning plan, thus simplifying each subquestion and shortening the reasoning path. ii) The EWO-guided exploration helps the system identify relevant paths early, minimizing unnecessary exploration.

# 5.3 Effectiveness and Efficiency Evaluation

(RQ4) Does PRoH stay effective on long-range multi-hop questions? We further evaluate PRoH on 200 additional long-range

questions per domain (3-6 hops). As shown in Table 4, PRoH sustains strong performance under these long-range settings, outperforming HyperGraphRAG by an average of  $26.68\%$  and up to  $44.87\%$  in F1 in the CS domain, as well as by an average of  $12.11\%$  and up to  $21.28\%$  in G-E. For the R-S score, PRoH achieves an average of  $1.14\%$  and up to  $6.59\%$  improvement in the Legal domain. The variant PRoH-L, also demonstrates strong performance under these long-range settings, outperforming HyperGraphRAG by an average of  $15.11\%$  and up to  $32.15\%$  in F1 score. The robustness of PRoH is also supported by the results in Figure 4, which analyzes the effect of ground truth context length (the number of knowledge fragments used when the question and golden answer are generated) on PRoH's performance. The F1 scores remain stable as the context length grows, suggesting that PRoH can maintain reasoning coherence even when the relevant knowledge spans multiple hops, demonstrating its robustness in long-range, multi-hop reasoning.

(RQ5) How does PRoH perform with multiple entities in the ground-truth context? Figure 5 reports the average F1 scores of PRoH across different levels of relational complexity in the questions. The complexity is measured by the number of entities participating in the ground-truth context for the question. Overall, PRoH maintains stable performance as the number of entities increases, which suggests that PRoH effectively handles moderately complex relational structures.

(RQ6) Is PRoH-L cost efficient in token usage? As shown in Table 3, PRoH-L demonstrates notable efficiency in token usage while maintaining competitive performance across all domains. Compared with HyperGraphRAG, PRoH-L significantly reduces the number of tokens used (input + output) per question, with the largest savings observed in the Computer Science domain at  $34.82\%$ . Despite the reduced token budget, PRoH-L achieves consistent F1 improvements with up to  $16.58\%$  in Agriculture. The only exception appears in the Legal domain, where token consumption increases for PRoH-L; however, this increase still yields a positive F1 gain of  $7.59\%$ . Overall, these results confirm that PRoH-L achieves a superior balance between efficiency and accuracy, offering a cost-effective alternative to full PRoH.

To further evaluate the effectiveness and efficiency of PRoH, we conduct additional experiments on its state search strategy and plan depth, and analyze the token usage across modules. We also conducted a case study on PRoH's structured question decomposition. Detailed results are provided in Appendix C.

# 6 Conclusion

This paper presents PRoH, a dynamic Knowledge Hypergraph-based RAG framework for multi-hop question answering. By introducing context-aware planning, structured iterative question decomposition and an Entity-Weighted Overlap(EWO)-guided reasoning path retrieval strategy, PRoH enables adaptive planning and reasoning on Knowledge Hypergraphs with beyond binary relational structures. Experimental results demonstrate that PRoH achieves state-of-the-art performance across multiple knowledge domains, surpassing the prior SOTA HyperGraphRAG by an average of  $19.73\%$  in F1 and  $8.41\%$  in Generation Evaluation (G-E) score, while maintaining high robustness in long-range multi-hop reasoning tasks.

# References

[1] Kurt D. Bollacker, Colin Evans, Praveen K. Paritosh, Tim Sturge, and Jamie Taylor. 2008. Freebase: a collaboratively created graph database for structuring human knowledge. In SIGMOD Conference. ACM, 1247-1250.  
[2] Boyu Chen, Zirui Guo, Zidan Yang, Yuluo Chen, Junze Chen, Zhenghao Liu, Chuan Shi, and Cheng Yang. 2025. PathRAG: Pruning Graph-based Retrieval Augmented Generation with Relational Paths. CoRR abs/2502.14902 (2025).  
[3] Liyi Chen, Panrong Tong, Zhongming Jin, Ying Sun, Jieping Ye, and Hui Xiong. 2024. Plan-on-Graph: Self-Correcting Adaptive Planning of Large Language Model on Knowledge Graphs. In Advances in Neural Information Processing Systems 38: Annual Conference on Neural Information Processing Systems 2024, NeurIPS 2024, Vancouver, BC, Canada, December 10 - 15, 2024, Amir Globersons, Lester Mackey, Danielle Belgrave, Angela Fan, Ulrich Paquet, Jakub M. Tomczak, and Cheng Zhang (Eds.).  
[4] Chengfeng Dou, Ying Zhang, Zhi Jin, Wenpin Jiao, Haiyan Zhao, Yongqiang Zhao, and Zhengwei Tao. 2025. Enhancing LLM Generation with Knowledge Hypergraph for Evidence-Based Medicine. CoRR abs/2503.16530 (2025).  
[5] Darren Edge, Ha Trinh, Newman Cheng, Joshua Bradley, Alex Chao, Apurva Mody, Steven Truitt, Dasha Metropolitansky, Robert Osazuwa Ness, and Jonathan Larson. 2024. From local to global: A graph rag approach to query-focused summarization. arXiv preprint arXiv:2404.16130 (2024).  
[6] Bahare Fatemi, Perouz Taslakian, David Vázquez, and David Poole. 2020. Knowledge Hypergraphs: Prediction Beyond Binary Relations. In *IJCAI. ijcai.org*, 2191-2197.  
[7] Yifan Feng, Hao Hu, Xingliang Hou, Shiquan Liu, Shihui Ying, Shaoyi Du, Han Hu, and Yue Gao. 2025. Hyper-RAG: Combating LLM Hallucinations using Hypergraph-Driven Retrieval-Augmented Generation. arXiv preprint arXiv:2504.08758 (2025).  
[8] Junqi Gao, Xiang Zou, Ying Ai, Dong Li, Yichen Niu, Biqing Qi, and Jianxing Liu. 2025. Graph Counselor: Adaptive Graph Exploration via Multi-Agent Synergy to Enhance LLM Reasoning. In ACL (1). Association for Computational Linguistics, 24650-24668.  
[9] Saiping Guan, Xiaolong Jin, Yuanzhuo Wang, and Xueqi Cheng. 2019. Link Prediction on N-ary Relational Data. In WWW. ACM, 583-593.  
[10] Zirui Guo, Lianghao Xia, Yanhua Yu, Tu Ao, and Chao Huang. 2024. Lighthrag: Simple and fast retrieval-augmented generation. arXiv preprint arXiv:2410.05779 (2024).  
[11] Bernal Jimenez Gutierrez, Yiheng Shu, Yu Gu, Michihiro Yasunaga, and Yu Su. 2024. Hipporag: Neurobiologically inspired long-term memory for large language models. Advances in Neural Information Processing Systems 37 (2024), 59532-59569.  
[12] Bernal Jimenez Gutierrez, Yiheng Shu, Weijian Qi, Sizhe Zhou, and Yu Su. 2025. From rag to memory: Non-parametric continual learning for large language models. arXiv preprint arXiv:2502.14802 (2025).  
[13] Haoyu Han, Yu Wang, Harry Shomer, Kai Guo, Jiayuan Ding, Yongjia Lei, Mahantesh Halappanavar, Ryan A. Rossi, Subhabrata Mukherjee, Xianfeng Tang, Qi He, Zhigang Hua, Bo Long, Tong Zhao, Neil Shah, Amin Javari, Yinglong Xia, and Jiliang Tang. 2025. Retrieval-Augmented Generation with Graphs (GraphRAG). CoRR abs/2501.00309 (2025).  
[14] Jinhao Jiang, Kun Zhou, Xin Zhao, and Ji-Rong Wen. 2023. UniKGQA: Unified Retrieval and Reasoning for Solving Multi-hop Question Answering Over Knowledge Graph. In ICLR. OpenReview.net.  
[15] Xinke Jiang, Ruizhe Zhang, Yongxin Xu, Rihong Qiu, Yue Fang, Zhiyuan Wang, Jinyi Tang, Hongxin Ding, Xu Chu, Junfeng Zhao, and Yasha Wang. 2025. HyKGE: A Hypothesis Knowledge Graph Enhanced RAG Framework for Accurate and Reliable Medical LLMs Responses. In ACL (1). Association for Computational Linguistics, 11836-11856.

[16] Jiho Kim, Yeonsu Kwon, Yohan Jo, and Edward Choi. 2023. KG-GPT: A General Framework for Reasoning on Knowledge Graphs Using Large Language Models. In Findings of the Association for Computational Linguistics: EMNLP 2023.  
[17] Xujian Liang and Zhaoquan Gu. 2025. Fast Think-on-Graph: Wider, Deeper and Faster Reasoning of Large Language Model on Knowledge Graph. In AAAI. AAAI Press, 24558-24566.  
[18] Runxuan Liu, Luobei Luobei, Jiaqi Li, Baoxin Wang, Ming Liu, Dayong Wu, Shijin Wang, and Bing Qin. 2025. Ontology-Guided Reverse Thinking Makes Large Language Models Stronger on Knowledge Graph Question Answering. In ACL (1). Association for Computational Linguistics, 15269-15284.  
[19] Haoran Luo, Guanting Chen, Yandan Zheng, Xiaobao Wu, Yikai Guo, Qika Lin, Yu Feng, Zemin Kuang, Meina Song, Yifan Zhu, et al. 2025. HyperGraphRAG: Retrieval-Augmented Generation via Hypergraph-Structured Knowledge Representation. arXiv preprint arXiv:2503.21322 (2025).  
[20] Linhao Luo, Yuan-Fang Li, Gholamreza Haffari, and Shirui Pan. 2024. Reasoning on Graphs: Faithful and Interpretable Large Language Model Reasoning. In ICLR. OpenReview.net.  
[21] Linhao Luo, Zicheng Zhao, Chen Gong, Gholamreza Haffari, and Shirui Pan. 2024. Graph-constrained Reasoning: Faithful Reasoning on Knowledge Graphs with Large Language Models. CoRR abs/2410.13080 (2024).  
[22] Jie Ma, Zhitao Gao, Qi Chai, Wangchun Sun, Pinghui Wang, Hongbin Pei, Jing Tao, Lingyun Song, Jun Liu, Chen Zhang, and Lizhen Cui. 2025. Debate on Graph: A Flexible and Reliable Reasoning Framework for Large Language Models. In AAAI. AAAI Press, 24768-24776.  
[23] Shengjie Ma, Chengjin Xu, Xuhui Jiang, Muzhi Li, Huaren Qu, Cehao Yang, Jiaxin Mao, and Jian Guo. 2025. Think-on-Graph 2.0: Deep and Faithful Large Language Model Reasoning with Knowledge-guided Retrieval Augmented Generation. In ICLR. OpenReview.net.  
[24] Costas Mavromatis and George Karypis. 2025. GNN-RAG: Graph Neural Retrieval for Efficient Large Language Model Reasoning on Knowledge Graphs. In ACL (Findings). Association for Computational Linguistics, 16882-16699.  
[25] Boci Peng, Yun Zhu, Yongchao Liu, Xiaohe Bo, Haizhou Shi, Chuntao Hong, Yan Zhang, and Siliang Tang. 2024. Graph Retrieval-Augmented Generation: A Survey. CoRR abs/2408.08921 (2024).  
[26] Paolo Rosso, Dingqi Yang, and Philippe Cudre-Mauroux. 2020. Beyond Triplets: Hyper-Relational Knowledge Graph Embedding for Link Prediction. In WWW. ACM / IW3C2, 1885–1896.  
[27] Apoorv Saxena, Aditay Tripathi, and Partha P. Talukdar. 2020. Improving Multi-hop Question Answering over Knowledge Graphs using Knowledge Base Embeddings. In ACL. Association for Computational Linguistics, 4498-4507.  
[28] Jiashuo Sun, Chengjin Xu, Lumingyuan Tang, Saizhuo Wang, Chen Lin, Yeyun Gong, Lionel M. Ni, Heung-Yeung Shum, and Jian Guo. 2024. Think-on-Graph: Deep and Responsible Reasoning of Large Language Model on Knowledge Graph. In The Twelfth International Conference on Learning Representations, ICLR 2024, Vienna, Austria, May 7-11, 2024. OpenReview.net.  
[29] Xingyu Tan, Xiaoyang Wang, Qing Liu, Xiwei Xu, Xin Yuan, and Wenjie Zhang. 2025. Paths-over-Graph: Knowledge Graph Empowered Large Language Model Reasoning. In WWW. ACM, 3505–3522.  
[30] Denny Vrandecic and Markus Krötzsch. 2014. Wikidata: a free collaborative knowledgebase. Commun. ACM 57, 10 (2014), 78-85. doi:10.1145/2629489  
[31] Changjian Wang, Weihong Deng, Weili Guan, Quan Lu, and Ning Jiang. 2025. Cross-Granularity Hypergraph Retrieval-Augmented Generation for Multi-hop Question Answering. CoRR abs/2508.11247 (2025).  
[32] Jianfeng Wen, Jianxin Li, Yongyi Mao, Shini Chen, and Richong Zhang. 2016. On the Representation and Embedding of Knowledge Bases beyond Binary Relations. In JJCAI. IJCAI/AAAI Press, 1300-1307.  
[33] Junde Wu, Jiayuan Zhu, Yunli Qi, Jingkun Chen, Min Xu, Filippo Menolascina, Yueming Jin, and Vicente Grau. 2025. Medical Graph RAG: Evidence-based Medical Large Language Model via Graph Retrieval-Augmented Generation. In ACL (1). Association for Computational Linguistics, 28443-28467.  
[34] Derong Xu, Xinhang Li, Ziheng Zhang, Zhenxi Lin, Zhihong Zhu, Zhi Zheng, Xian Wu, Xiangyu Zhao, Tong Xu, and Enhong Chen. 2025. Harnessing large language models for knowledge graph question answering via adaptive multi-aspect retrieval-augmentation. In Proceedings of the Thirty-Ninth AAAI Conference on Artificial Intelligence and Thirty-Seventh Conference on Innovative Applications of Artificial Intelligence and Fifteenth Symposium on Educational Advances in Artificial Intelligence.  
[35] Qinggang Zhang, Shengyuan Chen, Yuanchen Bei, Zheng Yuan, Huachi Zhou, Zijin Hong, Junnan Dong, Hao Chen, Yi Chang, and Xiao Huang. 2025. A Survey of Graph Retrieval-Augmented Generation for Customized Large Language Models. CoRR abs/2501.13958 (2025).  
[36] Yuyu Zhang, Hanjun Dai, Zornitsa Kozareva, Alexander J. Smola, and Le Song. 2018. Variational Reasoning for Question Answering With Knowledge Graph. In AAAI. AAAI Press, 6069-6076.  
[37] Qi Zhao, Hongyu Yang, Qi Song, Xin-Wei Yao, and Xiangyang Li. 2025. Know-Path: Knowledge-enhanced Reasoning via LLM-generated Inference Paths over Knowledge Graphs. CoRR abs/2502.12029 (2025).

[38] Ruilin Zhao, Feng Zhao, Long Wang, Xianzhi Wang, and Guandong Xu. 2024. KG-CoT: Chain-of-Thought Prompting of Large Language Models over Knowledge Graphs for Knowledge-Aware Question Answering. In Proceedings of the Thirty-Third International Joint Conference on Artificial Intelligence, IJCAI-24.  
[39] Xiangrong Zhu, Yuexiang Xie, Yi Liu, Yaliang Li, and Wei Hu. 2025. Knowledge Graph-Guided Retrieval Augmented Generation. In Proceedings of the 2025 Conference of the Nations of the Americas Chapter of the Association for Computational Linguistics: Human Language Technologies (Volume 1: Long Papers).  
[40] Zulun Zhu, Tiancheng Huang, Kai Wang, Junda Ye, Xinghe Chen, and Siqiang Luo. 2025. Graph-based Approaches and Functionalities in Retrieval-Augmented Generation: A Comprehensive Survey. CoRR abs/2504.10499 (2025).

# A Algorithm

# A.1 Plan Initialization

We summarize the comprehensive algorithmic procedure of reasoning plan initialization as shown in Algorithm 1.

Algorithm 1: PlanInit  
Input : Question Subgraph  $\mathcal{H}_q(\mathcal{V}_q, \mathcal{E}_q)$ , Question  $q$ , Topic Entities  $\mathcal{T}$ , Target Hyperedges  $\mathcal{R}$ , Plan Depth  $d_p$ , #Initial Plans  $n_0$   
1, Output : Set of initial DAGs  $\mathcal{D}_0$   
2  $\mathcal{H}_p(\mathcal{V}_p, \mathcal{E}_p) \gets (\emptyset, \emptyset)$ ;  
3  $\mathcal{F}_e \gets \{e \mid v \in e \land v \in \mathcal{T}\} \cup \mathcal{R}$ ;  
4 for  $d \gets 1$  to  $d_p$  do  
5  $\mathcal{F}_e' \gets \emptyset$ ;  
6 for each  $e \in \mathcal{F}_e$  do  
7  $\begin{array}{c} F_{\mathrm{cand}} \gets \emptyset; \\ F_{\mathrm{cand}} \gets \emptyset; \\ F_{\mathrm{cand}} \gets \emptyset; \\ F_{\mathrm{cand}} \gets \emptyset; \\ F_{\mathrm{cand}} \gets \emptyset; \\ F_{\mathrm{cand}} \gets \emptyset; \\ F_{\mathrm{cand}} \gets \emptyset; \\ F_{\mathrm{cand}} \leftarrow \text{RankSelectDirections}(F_{\mathrm{cand}}); \\ F_e' \gets F_e' \cup F_{\mathrm{sel}}; \\ V_p \gets V_p \cup \{v \mid v \in e \land e \in F_{\mathrm{sel}}\}; \\ \mathcal{E}_p \gets \mathcal{E}_p \cup F_{\mathrm{sel}}; \\ F_e' \gets F_e'; \\ c_p \leftarrow \text{FormPlanContext}(\mathcal{H}_p); \mathcal{D}_0 \leftarrow \emptyset; \\ q, L \leftarrow LLM(q, T, c_p); D \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0 \cup \{D\}; \\ Q, L \leftarrow LLM(q, T, c_p); D \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0 \cup \{D\}; \\ Q, L \leftarrow LLM(q, T, c_p); D \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0 \cup \{D\}; \\ Q, L \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0 \cup \{D\}; \\ Q, L \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0 \cup \{D\}; \\ Q, L \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0 \cup \{D\}; \\ q, L \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0 \cup \{D\}; \\ q, L \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0 \cup \{D\}; \\ q, L \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0 \cup \{D\} ; \\ q, L \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0 \cup \{D\} ; \\ q, L \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0 \cup \{D\} ; \\ q, L \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0 \cup (D - 1) ; \\ q, L \leftarrow T o p S o r t(Q, L); D_0 \leftarrow D_0$

# A.2 Reasoning

We summarize the comprehensive algorithmic procedure of reasoning as shown in Algorithm 2.

Algorithm 2: Reasoning  
Input : Initial DAGs  $\mathcal{D}_0$ , Question Subgraph  $\mathcal{H}_q$ , KH Exploration Depth Limit  $d_{\mathrm{max}}$ , Max #Solutions  $K$   
Output : Completed DAGs  $\mathcal{D}_{\mathrm{comp}}$   
1  $\mathcal{D}_{\mathrm{comp}} \gets \emptyset$ ;  
2  $\mathcal{F} \gets \mathcal{D}_0$ ;  
3 while  $\mathcal{F} \neq \emptyset$  and  $|\mathcal{D}_{\mathrm{comp}}| < K$  do  
4  $\begin{array}{l} D \leftarrow \mathcal{F}.pop(); \\ i \leftarrow D.\text{completed\_level} + 1; \\ \text{if } i \geq |D.\text{levels}| \text{ then} \\ \mathcal{D}_{\mathrm{comp}} \leftarrow \mathcal{D}_{\mathrm{comp}} \cup \{D\}; \\ \text{continue} \\ Q_i \leftarrow \text{subquestions at level } i \text{ of } D; \\ \mathcal{AP}_i \leftarrow \emptyset; \\ \text{for each } q_j \in Q_i \text{ do} \\ AP_j \leftarrow \text{RetrieveAnswersWithPaths}(\mathcal{H}_q, q_j, d_{\mathrm{max}}); \\ \mathcal{AP}_i[j] \leftarrow AP_j; \\ \text{for each combination of answers AP in } \mathcal{AP}_i \text{ do} \\ D_{\mathrm{new}} \leftarrow \text{LLMGenerateNewDAG}(D, \mathcal{AP}); \\ F.push(D_{\mathrm{new}}); \\ \end{array}$   
17 return  $\mathcal{D}_{\mathrm{comp}}$ ;

# A.3 Answer and Path Retrieval

We summarize the comprehensive algorithmic procedure of answer and path retrieval as shown in Algorithm 3.

Algorithm 3: RetrieveAnswersWithPaths  
Input:Question Subgraph  $\mathcal{H}_q(\mathcal{V}_q,\mathcal{E}_q)$  ,Subquestion  $q_{j}$  KH Exploration Depth Limit  $d_{\mathrm{max}}$  ,Beam Width b   
Output:Set of Step Answer - Reasoning Path Pair  $AP_{j}$    
// Graph re-anchoring   
1  $\mathcal{T}_j\gets$  TopicEntityInit  $(q_j,\mathcal{H}_q)$  .   
2  $\mathcal{R}_j\gets$  TargetHyperedgeMatch  $(q_j,\mathcal{H}_q)$  .   
// Initialize frontier   
3  $\mathcal{F}_e\gets \emptyset ,\mathcal{P}\gets \emptyset$  .   
4 for each  $e\in \{e\mid v\in e\land v\in \mathcal{T}_j\} \cup \mathcal{R}_j$  do   
5  $\begin{array}{r}\mathcal{F}_e\leftarrow \mathcal{F}_e\cup \{(e,[e])\} ;\\ \mathcal{P}\leftarrow \mathcal{P}\cup \{[e]\} ; \end{array}$    
6   
7 for  $d\gets 1$  to  $d_{\mathrm{max}}$  do   
8 // Beam search from current frontier   
 $F_{\mathrm{cand}}\gets \emptyset$    
9 for each  $(e,p_e)\in \mathcal{F}_e$  do   
for each  $e^{\prime}\in \mathrm{Nbr}(e)$  do   
 $S_{v} =$  {ScoreEntityWithLLM(v,  $q_{j})$  |  $v\in V(e)\cap V(e^{\prime})$  };   
 $s_e'\gets$  Aggregate(  $S_{v}$  );   
 $p_{e^{\prime}}\gets p_{e}\oplus [e^{\prime}];$ $F_{\mathrm{cand}}\gets F_{\mathrm{cand}}\cup \{(p_{e^{\prime}},s_{e^{\prime}})\}$  .   
 $F_{\mathrm{cand}}\gets$  RankSelectDirections(Fcand);   
 $F_{\mathrm{sel}}\gets$  LLMSelectDirections(Fcand,  $q_{j},b)$  .   
update  $\mathcal{F}_e$  and  $\mathcal{P}$  with  $F_{\mathrm{sel}}$  ..   
// Form and select reasoning paths   
 $P_{\mathrm{cand}}\gets$  FormPaths(P);   
 $P_{\mathrm{cand}}\gets$  RankSelectPaths(Pcand);   
 $P_{\mathrm{sel}}\gets$  LLMSelectPaths(Pcand,  $q_{j}$  );   
if  $P_{sel}\neq \emptyset$  then   
// Attempt subquestion   
 $AP_j\gets \emptyset$  .   
for each  $p_j\in P_{sel}$  do   
 $c_{j}\gets$  KnowledgeFusion(pj);   
 $a_j\gets$  LLMAnswerStep(cj,qj);   
 $AP_j\gets AP_j\cup \{(a_j,p_j)\}$  .   
return  $AP_j$

Table 5: Performance vs. State Search Strategy.  

<table><tr><td rowspan="2"># Init
n0</td><td rowspan="2"># Soln
K</td><td colspan="3">BFS</td><td colspan="3">DFS</td></tr><tr><td>F1</td><td>wT</td><td>VT</td><td>F1</td><td>wT</td><td>VT</td></tr><tr><td>1</td><td>1</td><td>57.86</td><td>28.00</td><td>8.31</td><td>55.52</td><td>11.83</td><td>3.29</td></tr><tr><td>1</td><td>2</td><td>56.93</td><td>41.37</td><td>9.70</td><td>53.22</td><td>12.88</td><td>4.50</td></tr><tr><td>1</td><td>3</td><td>57.70</td><td>18.58</td><td>9.24</td><td>57.16</td><td>12.65</td><td>5.67</td></tr><tr><td>2</td><td>2</td><td>54.80</td><td>44.62</td><td>14.02</td><td>54.98</td><td>10.21</td><td>4.77</td></tr><tr><td>2</td><td>3</td><td>58.58</td><td>39.13</td><td>15.15</td><td>57.15</td><td>10.04</td><td>6.24</td></tr><tr><td>3</td><td>3</td><td>61.94</td><td>126.85</td><td>20.56</td><td>58.48</td><td>12.25</td><td>6.58</td></tr></table>

# B Experiment Details

Baselines. We compare PRoH against five baselines: LLM-only, which directly generates answers using the intrinsic knowledge of the LLM; StandardRAG, a traditional chunk-based RAG approach; PathRAG [2]; HippoRAG2 [12]; and the state-of-the-art HyperGraphRAG [19]. Since HyperGraphRAG is the current SOTA we directly refer to their results and those of other baselines reported in their paper for comparisons.

Experimental Settings. Experiments are conducted using sophnet/Qwen3-30B-A3B-Thinking-25070-mini as the LLM, and Qwen/Qwen3-Embedding-0.6B for vector embedding. For PRoH, we set plan depth  $d_p = 3$ , KH exploration depth limit  $d_{max} = 3$ , number of initial plans  $n_0 = 2$ , max number of solutions  $K = 2$ . For PRoH-L, we set plan depth  $d_p = 2$ , KH exploration depth limit  $d_{max} = 3$ , number of initial plans  $n_0 = 1$ , max number of solutions  $K = 1$ .

# C Additional Experiment

# C.1 Ablation Study

(RQ7) How does the state search strategy affect the performance of PRoH? For this experiment, we randomly sampled 200 questions from the Medicine domain and compare breadth-first (BFS) and depth-first (DFS) state search strategies under different settings of  $n_0$ , the number of initial plans, and  $K$ , the maximum number of solutions. As reported in Table 5, BFS consistently achieves higher F1 scores than DFS, however this performance advantage comes with significant extra computational cost. When  $n_0 = 3$  and  $K = 3$ , BFS exhibits explosive growth in search width, it also visits 20.56 states in average, which is more than 3x of the DFS strategy. DFS though, as expected has a much stable width. Also, when we fix one of  $n_0$  or  $K$ , increasing the other will always improve F1 score for both strategies. Overall, DFS offers a better performance-to-cost ratio as shows a more stable scaling behavior.

(RQ8) How does the plan depth affect the state search tree? As shown in Table 6, increasing the plan depth consistently improves both F1 and G-E scores. When  $d_p$  increases from 1 to 3, F1 and G-E rise from  $55.65\%$  to  $59.47\%$  and from  $67.71\%$  to  $70.45\%$ , respectively. This indicates that deeper plan depth provides more comprehensive context for planning. The average peak search tree depth  $\hat{d}_T$  increases when  $d_p$  increases from 1 to 2 and then decreases to 1.360 when  $d_p = 3$ , suggesting that, with a richer planning context, a more efficient plan can be generated. Overall, deeper plan depth  $d_p$  enhances performance without introducing excessive reasoning complexity through question decomposition.

Table 6: Performance vs. plan depth  ${d}_{p}$  .  

<table><tr><td>Metrics</td><td>F1</td><td>G-E</td><td>dT</td></tr><tr><td>1</td><td>55.65</td><td>67.71</td><td>1.375</td></tr><tr><td>dp=2</td><td>57.13</td><td>68.57</td><td>1.415</td></tr><tr><td>3</td><td>59.47</td><td>70.45</td><td>1.360</td></tr></table>

![](images/f14fb011f8990e1865561b329036e6e3f154d87f8327874390458b839140f89c.jpg)  
Figure 6: Token Usage among Modules.

# C.2 Efficiency Evaluation

(RQ9) How does token usage vary across reasoning modules? Figure 6 reports the average token usage of PRoH across five domains, segmented by reasoning module. Overall, Answer and Path Retrieval dominates token consumption, indicating that most computational effort is spent retrieving and integrating intermediate reasoning states. Plan Initialization and State Search show moderate usage, reflecting the cost of constructing and exploring internal representations prior to retrieval. Final Answer Generation consistently requires fewer tokens, suggesting that linguistic synthesis is relatively lightweight compared to reasoning. Graph Anchoring contributes minimally, serving as a brief setup phase. These trends imply that PRoH's efficiency is primarily determined by retrieval and reasoning dynamics rather than generation overhead.

# C.3 Case study: Structured Question Decomposition

In this section, we present Table 7, which illustrates PRoH's structured question decomposition mechanism. It also demonstrates PRoH's effectiveness in handling multi-entity and multi-hop question answering tasks.

Table 7: Example of Planning and Reasoning of PRoH.  

<table><tr><td>Field</td><td>Content</td></tr><tr><td>Question</td><td>What must be prepared in accordance with GAAP for financial and tax reporting purposes?</td></tr><tr><td>Golden Answer</td><td>FINANCIAL STATEMENTS</td></tr><tr><td>Context</td><td>(1) The books of the Partnership shall be maintained, for financial and tax reporting purposes, on an accrual basis in accordance with GAAP.</td></tr><tr><td></td><td>(2) 1ACCOUNTING AND OTHER TERMS</td></tr><tr><td></td><td>(3) all accounting terms used herein shall be interpreted, all accounting determinations hereunder shall be made, and all financial statements required to be delivered hereunder shall be prepared in accordance with GAAP as in effect from time to time.</td></tr><tr><td>nary</td><td>2</td></tr><tr><td>nhop</td><td>3</td></tr><tr><td>DAG Edges</td><td>0 → 1, 0 → 2</td></tr><tr><td>Subquestion 0</td><td>Subquestion: What does GAAP stand for?</td></tr><tr><td></td><td>Topics: &quot;GAAP&quot;</td></tr><tr><td></td><td>Level: 0</td></tr><tr><td></td><td>Answer: Generally Accepted Accounting Principles</td></tr><tr><td></td><td>Reasoning Path: &quot;GAAP&quot; means U.S. generally accepted accounting principles.&quot;</td></tr><tr><td>Subquestion 1</td><td>Subquestion: What standards do GAAP require for financial reporting?</td></tr><tr><td></td><td>Topics: &quot;GAAP&quot;, &quot;FINANCIAL REPORTING&quot;</td></tr><tr><td></td><td>Level: 1</td></tr><tr><td></td><td>Answer: GAAP requires financial statements to be prepared in accordance with its principles, ensuring accurate representation of a company&#x27;s financial health.</td></tr><tr><td></td><td>Reasoning Path: &quot;All financial statements required to be delivered hereunder shall be prepared in accordance with GAAP.&quot;</td></tr><tr><td>Subquestion 2</td><td>Subquestion: What standards do GAAP require for tax reporting?</td></tr><tr><td></td><td>Topics: &quot;GAAP&quot;, &quot;TAX REPORTING&quot;</td></tr><tr><td></td><td>Level: 1</td></tr><tr><td></td><td>Answer: Generally Accepted Accounting Principles (GAAP) require accurate and consistent reporting of financial information in compliance with applicable tax laws and regulations.</td></tr><tr><td></td><td>Reasoning Path: &quot;The Company maintains internal controls over financial reporting... sufficient to provide reasonable assurance that transactions are recorded as necessary to permit preparation of financial statements for external purposes in accordance with GAAP.&quot;</td></tr><tr><td></td><td>-&gt; &quot;hyperedge&quot;(xxvii) Since December 31, 2019, the Association has not: (A) changed its tax reporting or accounting policies or practices; (B) settled or compromised any liability for taxes or made or rescinded any tax election; (C) incurred any debt except in the ordinary course of business; (D) suffered any theft.&quot;</td></tr><tr><td>PRoH answer</td><td>Answer: Financial statements</td></tr><tr><td></td><td>Reasoning: The question asks about what is prepared in accordance with GAAP for financial and tax reporting purposes. The context specifies that financial statements must be prepared in accordance with GAAP, which dictates how financial transactions are recorded and presented. This indicates that financial statements are the expected answer.</td></tr></table>