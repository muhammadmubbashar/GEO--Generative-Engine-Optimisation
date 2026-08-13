"""
geo_bench — a controlled benchmark for Generative Engine Optimisation.

Study: does content and structural optimisation change how often Flight Centre
is retrieved and cited by a retrieval-augmented answer engine?

Literature anchors
------------------
Aggarwal, Murahari et al. "GEO: Generative Engine Optimization." KDD 2024.
    arXiv:2311.09735 — two-step engine design, 5 samples at temperature 0.7,
    generation prompt, Position-Adjusted Word Count.
Puerto, Gubri et al. "C-SEO Bench: Does Conversational SEO Work?" NeurIPS 2025
    Datasets & Benchmarks. arXiv:2506.11097 — two-tailed testing,
    Bonferroni-Holm correction, retrieval position dominates content edits.

Package layout
--------------
    crawler/     acquire and freeze the corpus
    retrieval/   parse, chunk, embed, index, retrieve
    generation/  prompt construction and answer generation
    api/         LLM provider abstraction (offline | openai)
    evaluation/  metrics and statistics
    experiment/  orchestration and control tests
"""
__version__ = "0.1.0"
