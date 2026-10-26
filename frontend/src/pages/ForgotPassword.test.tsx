import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ForgotPassword } from './ForgotPassword';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <ForgotPassword />
    </MemoryRouter>
  );
});
