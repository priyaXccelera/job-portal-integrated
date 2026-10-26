import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LoginOtp } from './LoginOtp';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <LoginOtp />
    </MemoryRouter>
  );
});
