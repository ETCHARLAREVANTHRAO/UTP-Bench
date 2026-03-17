# UTP-Bench: Uncertainty-aware Travel Planning Benchmark

**UTP-Bench** is a large-scale benchmark for evaluating travel itinerary generation under real-world uncertainty. Unlike prior benchmarks that assume deterministic settings, it models disruptions such as transportation delays and crowd fluctuations using empirical data from 504 cities across 33 Indian states and union territories.

The dataset integrates attractions, accommodations, restaurants, and multi-modal transportation networks to simulate realistic planning scenarios. UTP-Bench introduces three robustness metrics: **Buffer Adequacy Score (BAS)**, **Crowd-Aware Timing Score (CATS)**, and **Transport Delay Absorption Score (TDAS)**.

Experiments with state-of-the-art LLMs (e.g., GPT-5, Qwen3-14B) reveal substantial gaps between model-generated and human-authored plans, particularly in temporal buffering, delay-aware scheduling, and crowd-sensitive planning.

UTP-Bench provides a standardized framework for developing and evaluating reliable, uncertainty-aware travel planning systems.
