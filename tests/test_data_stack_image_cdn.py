# @file tests/test_data_stack_image_cdn.py
# @description Verifies private S3 image delivery through CloudFront OAC and published CDN identifiers.
# @author JJonyeok2
# @lastModified 2026-07-15

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_STACK_TEMPLATE = PROJECT_ROOT / "infra" / "data-stack" / "template.yaml"


class DataStackImageCdnTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = DATA_STACK_TEMPLATE.read_text(encoding="utf-8")

    def _resource_block(self, resource_name: str, next_resource_name: str) -> str:
        start = self.template.index(f"  {resource_name}:")
        end = self.template.index(f"  {next_resource_name}:")
        return self.template[start:end]

    def test_image_bucket_stays_private_and_cloudfront_uses_oac(self):
        image_bucket = self._resource_block("ImageBucket", "ImageCloudFrontOriginAccessControl")
        oac = self._resource_block("ImageCloudFrontOriginAccessControl", "ImageCloudFrontDistribution")
        distribution = self._resource_block("ImageCloudFrontDistribution", "ImageBucketReadOnlyPolicy")

        for expected in (
            "BlockPublicAcls: true",
            "BlockPublicPolicy: true",
            "IgnorePublicAcls: true",
            "RestrictPublicBuckets: true",
        ):
            self.assertIn(expected, image_bucket)

        self.assertIn("OriginAccessControlOriginType: s3", oac)
        self.assertIn("SigningBehavior: always", oac)
        self.assertIn("SigningProtocol: sigv4", oac)
        self.assertIn("OriginAccessControlId: !Ref ImageCloudFrontOriginAccessControl", distribution)
        self.assertIn("DomainName: !GetAtt ImageBucket.RegionalDomainName", distribution)

    def test_image_cloudfront_endpoint_allows_only_get_and_head(self):
        distribution = self._resource_block("ImageCloudFrontDistribution", "ImageBucketReadOnlyPolicy")

        self.assertIn("ViewerProtocolPolicy: redirect-to-https", distribution)
        self.assertIn("Compress: true", distribution)
        self.assertIn("AllowedMethods:", distribution)
        self.assertIn("- GET", distribution)
        self.assertIn("- HEAD", distribution)
        self.assertNotIn("- POST", distribution)
        self.assertNotIn("- PUT", distribution)
        self.assertNotIn("- DELETE", distribution)
        self.assertNotIn("- PATCH", distribution)

    def test_image_bucket_policy_grants_cloudfront_get_object_only(self):
        bucket_policy = self._resource_block("ImageBucketReadOnlyPolicy", "RDSHostParameter")

        self.assertIn("Principal:", bucket_policy)
        self.assertIn("Service: cloudfront.amazonaws.com", bucket_policy)
        self.assertIn("Action: s3:GetObject", bucket_policy)
        self.assertIn("AWS:SourceArn:", bucket_policy)
        self.assertIn("distribution/${ImageCloudFrontDistribution}", bucket_policy)

        for forbidden_action in (
            "s3:PutObject",
            "s3:DeleteObject",
            "s3:DeleteObjectVersion",
            "s3:ListBucket",
            "s3:PutBucketPolicy",
            "s3:PutBucketPublicAccessBlock",
        ):
            self.assertNotIn(forbidden_action, bucket_policy)

    def test_image_cdn_identifiers_are_published_for_frontend_handoff(self):
        for expected in (
            "/lovv/${EnvName}/cloudfront/image_domain",
            "/lovv/${EnvName}/cloudfront/image_base_url",
            "ImageCdnDistributionId:",
            "ImageCdnDomainName:",
            "ImageCdnBaseUrl:",
            "https://${ImageCloudFrontDistribution.DomainName}",
        ):
            self.assertIn(expected, self.template)


if __name__ == "__main__":
    unittest.main()

# EOF: tests/test_data_stack_image_cdn.py
