docker build -t your-registry/aiops-monitor:latest .
docker push your-registry/aiops-monitor:latest

next change in deployment.yaml to use the new image version: your-registry/aiops-monitor:latest

kubectl apply -f monitoring/rbac.yaml
kubectl apply -f monitoring/deployment.yaml