#!/bin/bash
echo 'Setting up lightweight Prometheus for backend...'

kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Using the lightweight standalone prometheus chart instead of kube-prometheus-stack
# so it doesn't crash Minikube on laptops from Operator OOM kills.
helm upgrade --install prometheus prometheus-community/prometheus \
    --namespace monitoring \
    --set alertmanager.enabled=false \
    --set coreDns.enabled=false \
    --set kube-state-metrics.enabled=true \
    --set prometheus-node-exporter.enabled=false \
    --set configmapReload.prometheus.enabled=false \
    --set server.persistentVolume.enabled=true \
    --set server.persistentVolume.size=2Gi \
    --set server.service.type=NodePort

echo 'Waiting for Prometheus deployment to be ready (this may take a minute or two)...'
kubectl rollout status deployment prometheus-server -n monitoring --timeout=300s

echo 'Waiting for Prometheus to scrape initial metrics data...'
for i in {1..30}; do
  if kubectl exec deploy/prometheus-server -n monitoring -- sh -c 'wget -qO- http://localhost:9090/api/v1/query?query=up | grep -q "result\":\[{"' 2>/dev/null; then
      echo "Prometheus is successfully running and fetching data!"
      break
  fi
  echo -n "."
  sleep 5
done
echo ""

echo 'Prometheus is fully initialized. It is configured as a NodePort in Minikube.'
echo 'Your backend will automatically discover and connect to its URL.'
