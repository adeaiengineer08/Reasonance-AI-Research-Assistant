# Sample data

This folder ships with sample document corpora for Project 1 (AI Research Assistant).

## Project 1 corpora

- `sample-corpus/aws-docs/` - a curated subset of public AWS documentation (IAM, S3, Lambda, Bedrock).
- `sample-corpus/k8s-docs/` - a curated subset of Kubernetes documentation.
- `sample-corpus/anthropic-policy/` - publicly available Anthropic usage policy + privacy docs.

Each corpus is a flat directory of `.md` files. Each file's first line is the source URL as a comment, e.g.

```
<!-- source: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys_manage.html -->

# Managing access keys for IAM users
...
```

The ingestion script reads the source URL from this comment.

## How the corpora were built

Each corpus is hand-curated, public-domain, and small enough to embed in under a minute. We do NOT include scraped or copyrighted content.
