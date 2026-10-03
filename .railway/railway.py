from railway_sdk import define_railway, github, project, service

# This repository manages only its own resources in the environment. Other
# repositories export their own partial name.
# See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
PARTIAL = "AutoQA-Alpha-Target"

@define_railway
def main(ctx=None):
    target = service(
        "AutoQA-Alpha-Target",
        source=github("jayoffans/AutoQA-Alpha-Target", branch="main"),
        build={"builder": "DOCKERFILE", "dockerfilePath": "/Dockerfile"},
        healthcheck="/health",
        healthcheckTimeout=60,
        deploy={"restartPolicyType": "ON_FAILURE", "restartPolicyMaxRetries": 3},
    )
    return project("AutoQA-Alpha-Target", resources=[target])
