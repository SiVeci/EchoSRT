import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'intro',
    {
      type: 'category',
      label: '🚀 快速入门',
      items: [
        'getting-started/installation',
        'getting-started/quick-start',
        'getting-started/configuration',
      ],
    },
    {
      type: 'category',
      label: '📖 用户指南',
      items: [
        'user-guide/audio-extraction',
        'user-guide/workspace',
        {
          type: 'category',
          label: '语音识别',
          items: [
            'user-guide/speech-recognition/local-whisper',
            'user-guide/speech-recognition/online-asr',
          ],
        },
        'user-guide/translation',
        'user-guide/downloads',
      ],
    },
    {
      type: 'category',
      label: '🏗️ 系统架构',
      items: [
        'architecture/overview',
        'architecture/pipeline',
        'architecture/state-management',
        'architecture/websocket',
      ],
    },
    {
      type: 'category',
      label: '🔌 API 参考',
      items: [
        'api-reference/websocket-api',
        'api-reference/rest-api',
        'api-reference/javascript-sdk',
      ],
    },
    {
      type: 'category',
      label: '🚢 部署指南',
      items: [
        'deployment/docker',
        'deployment/gpu-setup',
        'deployment/proxy-config',
        'deployment/nas-guide',
      ],
    },
    {
      type: 'category',
      label: '🛠️ 开发手册',
      items: [
        'development/project-structure',
        'development/contributing',
        'development/changelog',
      ],
    },
  ],
};

export default sidebars;