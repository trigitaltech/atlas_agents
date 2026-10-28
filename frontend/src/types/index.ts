export type AgentConfig = {
  provider: "deterministic" | "openai" | "ollama";
  model: string;
  temperature: number;
  tools: string[];
};
export type Agent = {
  id: string;
  name: string;
  description: string;
  agent_type: string;
  enabled: boolean;
  configuration: AgentConfig;
  created_at: string;
};
export type Execution = {
  id: string;
  step_name: string;
  status: string;
  duration_ms: number;
  created_at: string;
  error_message: string | null;
};
export type Job = {
  id: string;
  agent_id: string;
  status: string;
  input_data: {
    url: string;
    instruction: string;
    fields: string[];
    agent_id?: string | null;
    max_depth?: number;
    max_pages?: number;
    timeout?: number;
    token_budget?: number;
    output_format?: string;
    render_js?: boolean;
    authorization_confirmed?: boolean;
    additional_authorized_domains?: string[];
  };
  context: {
    step?: string;
    pages?: number;
    records?: number;
    tokens?: number;
    approximate_cost?: number;
    stop_reason?: string;
    authorized_hostnames?: string[];
    error_code?: string;
    authorization_required_hostname?: string;
  };
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  executions?: Execution[];
};
export type RecordRow = {
  id: string;
  source_url: string;
  extracted_data: Record<string, string | null>;
  evidence: Record<string, string>;
  validation_status: string;
};
export type Tool = { name: string; description: string; permission: string };
export type Settings = {
  allowed_domains: string[];
  max_pages: number;
  max_timeout: number;
  max_tokens: number;
  rate_interval: number;
  browser_enabled: boolean;
  configuration_source: string;
};
