import type { CmsType, TenantContext } from "@queryclear/shared";

export interface DraftPublishRequest {
  tenant: TenantContext & { domainId: string };
  cmsType: CmsType;
  title: string;
  bodyHtml: string;
  schemaJson?: Record<string, unknown>;
}

export interface DraftPublishResult {
  externalId: string;
  status: "draft_created" | "failed";
  editUrl?: string;
}

export interface CmsConnector {
  readonly kind: CmsType;
  createDraft(request: DraftPublishRequest): Promise<DraftPublishResult>;
}

export class UnsupportedCmsConnector implements CmsConnector {
  constructor(readonly kind: CmsType) {}

  async createDraft(): Promise<DraftPublishResult> {
    return {
      externalId: "",
      status: "failed"
    };
  }
}
