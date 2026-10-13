# Loki Trading Platform - Kubernetes Deployment Guide

## Prerequisites

- Kubernetes cluster (v1.24+)
- kubectl configured
- Helm 3 installed
- Docker registry access

## Quick Start

### 1. Create Namespace
```bash
kubectl create namespace loki-trading
```

### 2. Create Secrets
```bash
# Create database secret
kubectl create secret generic loki-secrets \
  --from-literal=DATABASE_URL='postgresql://loki:password@timescaledb-service:5432/loki_trading' \
  --from-literal=REDIS_URL='redis://:password@redis-service:6379/0' \
  --from-literal=SECRET_KEY='your-secret-key-here' \
  --from-literal=DB_PASSWORD='your-db-password' \
  --from-literal=REDIS_PASSWORD='your-redis-password' \
  -n loki-trading
```

### 3. Deploy Application
```bash
kubectl apply -f kubernetes/deployment.yaml
```

### 4. Verify Deployment
```bash
kubectl get pods -n loki-trading
kubectl get services -n loki-trading
```

### 5. Access Application
```bash
# Get LoadBalancer IP
kubectl get service loki-api-service -n loki-trading

# Port forward for local testing
kubectl port-forward -n loki-trading service/loki-api-service 8000:80
```

## Production Configuration

### SSL/TLS Setup
Install cert-manager for automatic SSL certificates:
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
```

### Monitoring Setup
```bash
# Install Prometheus & Grafana
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack -n loki-trading
```

### Horizontal Scaling
The HPA automatically scales pods based on CPU/memory:
- Min: 3 pods
- Max: 10 pods
- Target CPU: 70%
- Target Memory: 80%

### Database Backup
```bash
# Backup TimescaleDB
kubectl exec -n loki-trading timescaledb-0 -- pg_dump -U loki loki_trading > backup.sql

# Restore
kubectl exec -i -n loki-trading timescaledb-0 -- psql -U loki loki_trading < backup.sql
```

## Troubleshooting

### Check Logs
```bash
kubectl logs -n loki-trading -l app=loki-api
kubectl logs -n loki-trading -l app=timescaledb
```

### Restart Pods
```bash
kubectl rollout restart deployment/loki-api -n loki-trading
```

### Scale Manually
```bash
kubectl scale deployment/loki-api --replicas=5 -n loki-trading
```

## Production Checklist

- [ ] Update secrets with strong passwords
- [ ] Configure SSL/TLS certificates
- [ ] Set up backup strategy
- [ ] Configure monitoring alerts
- [ ] Set resource limits appropriately
- [ ] Enable network policies
- [ ] Configure pod security policies
- [ ] Set up log aggregation
- [ ] Configure auto-scaling parameters
- [ ] Test disaster recovery procedures

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Load Balancer                         │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
    ┌────▼─────┐          ┌─────▼────┐
    │ Loki API │          │ Loki API │  (Replicas: 3-10)
    └────┬─────┘          └─────┬────┘
         │                      │
         └──────────┬───────────┘
                    │
         ┌──────────┴──────────┐
         │                     │
    ┌────▼─────┐         ┌────▼─────┐
    │TimescaleDB│         │  Redis   │
    │(StatefulSet)        │(Cache)   │
    └──────────┘         └──────────┘
```

## Support

For issues or questions:
- Documentation: https://docs.lokitrading.ai
- Email: support@lokitrading.ai
- GitHub: https://github.com/lokitrading/loki
