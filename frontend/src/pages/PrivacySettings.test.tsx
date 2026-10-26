import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PrivacySettings } from './PrivacySettings';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <PrivacySettings />
    </MemoryRouter>
  );
});
