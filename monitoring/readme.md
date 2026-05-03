docker build -t your-registry/aiops-monitor:v4 .
docker push your-registry/aiops-monitor:v4


kubectl apply -f monitoring/rbac.yaml
kubectl apply -f monitoring/deployment.yaml