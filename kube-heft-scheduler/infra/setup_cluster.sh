#!/usr/bin/env bash
# Jalankan dari root proyek (kube-heft-scheduler/): ./infra/setup_cluster.sh
set -euo pipefail

echo "[1/5] Building heft-worker:latest Docker image..."
docker build -t heft-worker:latest ./worker

echo "[2/5] Creating Kind cluster 'heft-datacenter' (1 Datacenter, 2 Hosts)..."
if kind get clusters | grep -q "^heft-datacenter$"; then
    echo "Cluster 'heft-datacenter' already exists. Skipping creation."
else
    kind create cluster --config ./infra/kind-config.yaml
fi

echo "[3/5] Loading heft-worker:latest image into Kind nodes..."
kind load docker-image heft-worker:latest --name heft-datacenter

echo "[4/5] Deploying 4 heterogeneous VM pods and NodePort services..."
kubectl apply -f ./infra/k8s-workers.yaml

echo "[5/5] Waiting for all 4 VM pods to be Ready..."
kubectl wait --for=condition=Ready pod -l app=heft-worker --timeout=180s

echo "=== Topology Verification ==="
kubectl get nodes -L topology.host
kubectl get pods -o wide
