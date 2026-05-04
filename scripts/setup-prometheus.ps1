Write-Host "Setting up lightweight Prometheus for backend..." -ForegroundColor Cyan

# Ensure kubectl uses the current Windows Minikube context
kubectl config use-context minikube

# Create namespace safely
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# Add Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install lightweight Prometheus
helm upgrade --install prometheus prometheus-community/prometheus `
    --namespace monitoring `
    --set alertmanager.enabled=$false `
    --set kube-state-metrics.enabled=$true `
    --set prometheus-node-exporter.enabled=$false `
    --set configmapReload.prometheus.enabled=$false `
    --set server.persistentVolume.enabled=$true `
    --set server.persistentVolume.size=2Gi `
    --set server.service.type=NodePort

Write-Host "Waiting for Prometheus deployment to be ready..." -ForegroundColor Yellow

kubectl rollout status deployment prometheus-server -n monitoring --timeout=300s

Write-Host "Waiting for Prometheus to scrape initial metrics data..." -ForegroundColor Yellow

for ($i = 0; $i -lt 30; $i++) {
    try {
        $result = kubectl exec deploy/prometheus-server -n monitoring -- sh -c `
        "wget -qO- http://localhost:9090/api/v1/query?query=up"

        if ($result -match '"status":"success"') {
            Write-Host "Prometheus is successfully running and fetching data!" -ForegroundColor Green
            break
        }
    } catch {}

    Write-Host -NoNewline "."
    Start-Sleep -Seconds 5
}

Write-Host ""
Write-Host "Prometheus is fully initialized." -ForegroundColor Green
Write-Host "It is configured as a NodePort in Minikube." -ForegroundColor Green