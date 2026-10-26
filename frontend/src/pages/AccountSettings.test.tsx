import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AccountSettings } from './AccountSettings';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <AccountSettings />
    </MemoryRouter>
  );
});
